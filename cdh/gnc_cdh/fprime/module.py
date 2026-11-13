"""A Basilisk Python `SysModel` running the WiseFsw F´ deployment in the simulation's process."""

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from gnc_cdh import UNITS
from gnc_cdh.basilisk import AlgorithmModule
from gnc_cdh.dictionary import Dictionary

__all__ = ["DICTIONARY", "FprimeModule", "extension"]

_NANOSECONDS_PER_SECOND = 1e9
_NANOSECONDS_PER_MICROSECOND = 1_000

DICTIONARY = Path(__file__).with_name("WiseFswTopologyDictionary.json")
"""The dictionary F´ generated for the deployment, copied here by `just fsw`."""

_ESTIMATE = {"q_BN": "nav.bodyEciAttitude", "r_BN_N": "nav.bodyEciPos", "v_BN_N": "nav.bodyEciVel"}
"""The channel each estimate a host records is read from."""

_loaded_stamp: tuple[int, int] | None = None
"""The extension file's inode and modification time, in ns, when this process first loaded it."""


def extension() -> ModuleType:
    """The deployment's extension, `_wise_fsw`, the one entry point to it.

    A process cannot reload an extension, so one rebuilt on disk after this process loaded it is
    refused rather than flown stale. The file is stamped on the first call, so an import of
    `_wise_fsw` that bypasses this goes unchecked.

    Returns:
        The extension module.

    Raises:
        ModuleNotFoundError: the extension is not built.
        RuntimeError: the extension file changed after this process loaded it.
    """
    global _loaded_stamp
    try:
        import gnc_cdh.fprime._wise_fsw as _wise_fsw
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError("the F´ deployment is not built; run `just fsw`") from error

    status = os.stat(_wise_fsw.__file__)
    stamp = (status.st_ino, status.st_mtime_ns)
    if _loaded_stamp is None:
        _loaded_stamp = stamp
    if stamp != _loaded_stamp:
        raise RuntimeError(
            f"{_wise_fsw.__file__} was rebuilt after this process loaded it;"
            " restart the kernel to fly the new build"
        )
    return _wise_fsw


class FprimeModule(sysModel.SysModel):
    """Runs the WiseFsw deployment each tick: the clock set, the IMU reading sent, the schedule run.

    The deployment is the WiseFsw topology, whose content is the dead reckoner. The channel each
    estimate is read from, `_ESTIMATE`, is the one dead-reckoner-specific piece of this host.
    The deployment is one per process, so one module flies at a time. `Reset` boots it at t = 0
    and gives the dead reckoner its initial state, handed over directly rather than by command.
    Each `UpdateState` after the last tick reads the IMU once, steps the deployment and logs
    every channel the tick wrote, serialized, by the tick's time in ns; `estimate_datasets`
    decodes them through the deployment's dictionary.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in, the Python
            host's, so the two builds fly at one rate.
        build: the host's build identity, recorded in a flight's `flight.json`: the host, F´'s
            version and the commit the deployment was built from.
    """

    period_s = AlgorithmModule.period_s
    build: dict[str, str]

    def __init__(
        self, imu: Any, mu: float, dcm_PB: np.ndarray, initial: Mapping[str, np.ndarray]
    ) -> None:
        """Holds what `Reset` boots the deployment with.

        Args:
            imu: the IMU reader, subscribed by the caller.
            mu: m^3/s^2, the central body's gravitational parameter.
            dcm_PB: (3, 3) the IMU's mounting [PB], v_P = [PB] v_B.
            initial: the dead reckoner's state at t = 0: `q0_BN` ((4,) quaternion W X Y Z), `r0_N`
                ((3,) m) and `v0_N` ((3,) m/s), in the shape of a scenario's `initial_state()`.
        """
        super().__init__()
        self._fsw = extension()
        self._imu = imu
        self._mu = float(mu)
        self._dcm_PB = np.asarray(dcm_PB, dtype=float)
        self._initial = {k: np.asarray(v, dtype=float) for k, v in initial.items()}
        self._dictionary = Dictionary(DICTIONARY)
        self.build = {
            "host": "gnc_cdh.fprime.FprimeModule",
            "frameworkVersion": self._dictionary.metadata["frameworkVersion"],
            "projectVersion": self._dictionary.metadata["projectVersion"],
        }
        self._t_ns = 0
        self._log: dict[int, Mapping[int, bytes]] = {}

    def Reset(self, CurrentSimNanos: int) -> None:
        """Boots the deployment, initializes the dead reckoner and logs the telemetry at t = 0.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            RuntimeError: the extension was rebuilt after this process loaded it, or the IMU
                reader is not subscribed.
        """
        self._fsw = extension()
        if not self._imu.isLinked():
            raise RuntimeError("the IMU reader is not subscribed to any message")
        self._t_ns = CurrentSimNanos
        self._fsw.boot(mu=self._mu, dcm_PB=self._dcm_PB)
        self._fsw.initialize_nav(
            t_ns=self._t_ns,
            q_BN=self._initial["q0_BN"],
            r_BN_N=self._initial["r0_N"],
            v_BN_N=self._initial["v0_N"],
        )
        self._log = {self._t_ns: self._fsw.telemetry()}

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the deployment to the current time when it lies after the last tick.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            RuntimeError: the tick is not at a whole microsecond, or the IMU reader has never
                been written.
        """
        if not CurrentSimNanos > self._t_ns:
            return
        if CurrentSimNanos % _NANOSECONDS_PER_MICROSECOND:
            raise RuntimeError(
                f"the tick at {CurrentSimNanos} ns is not a whole microsecond,"
                " which the deployment's clock cannot hold"
            )
        if not self._imu.isWritten():
            t = CurrentSimNanos / _NANOSECONDS_PER_SECOND
            raise RuntimeError(f"the IMU has not been written at t = {t} s")
        reading = self._imu()
        self._fsw.step(
            t_ns=CurrentSimNanos,
            angVelPlatform=np.array(reading.AngVelPlatform, dtype=float),
            accelPlatform=np.array(reading.AccelPlatform, dtype=float),
        )
        self._t_ns = CurrentSimNanos
        self._log[CurrentSimNanos] = self._fsw.telemetry()

    def fly(self, run: Callable[[Any, dict[str, tuple[Any, str, str]]], dict]) -> dict:
        """Flies the scenario through `run` and records the estimate from the telemetry log.

        Args:
            run: flies the scenario with this host and the datasets to record, as the harness
                binds it from the scenario and its stopping rule.

        Returns:
            The run's datasets with the estimate's added.
        """
        datasets = run(self, {})
        datasets.update(self.estimate_datasets(datasets["t_s"][0]))
        return datasets

    def estimate_datasets(self, t_s: np.ndarray) -> dict[str, tuple[np.ndarray, str]]:
        """The estimate's run-file datasets at the record times, from the logged telemetry.

        Args:
            t_s: (N,) s, the record times, each one a tick's time to the nanosecond.

        Returns:
            `est/q_BN` ((N, 4) quaternion W X Y Z), `est/r_BN_N` ((N, 3) m) and `est/v_BN_N`
            ((N, 3) m/s).

        Raises:
            KeyError: naming a record time no tick logged.
        """
        rows = []
        for t in t_s:
            t_ns = round(float(t) * _NANOSECONDS_PER_SECOND)
            if t_ns not in self._log:
                raise KeyError(f"no telemetry was logged at t = {t} s")
            rows.append(self._log[t_ns])
        values = {}
        for name, channel_name in _ESTIMATE.items():
            channel = self._dictionary.channel(channel_name)
            values[name] = channel.decode_many([row[channel.id] for row in rows])
        return {f"est/{name}": (value, UNITS[name]) for name, value in values.items()}
