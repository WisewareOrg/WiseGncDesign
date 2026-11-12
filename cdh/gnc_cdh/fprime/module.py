"""A Basilisk Python `SysModel` running the WiseFsw F´ deployment in the simulation's process."""

import json
import struct
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel
from scipy.spatial.transform import Rotation

from gnc_cdh.basilisk import UNITS, AlgorithmModule

__all__ = ["DICTIONARY", "FprimeModule", "decoders", "telemetry_by_name"]

_NANOSECONDS_PER_SECOND = 1e9
_NANOSECONDS_PER_MICROSECOND = 1_000

DICTIONARY = Path(__file__).with_name("WiseFswTopologyDictionary.json")
"""The dictionary F´ generated for the deployment, copied here by `just fsw`."""

_PRIMITIVES = {"F32": ">f", "F64": ">d", "I8": ">b", "I16": ">h", "I32": ">i", "I64": ">q"}
_PRIMITIVES |= {"U8": ">B", "U16": ">H", "U32": ">I", "U64": ">Q"}


def decoders(dictionary: Mapping[str, Any]) -> dict[int, tuple[str, Any]]:
    """Each telemetry channel's name and decoder, by channel ID, from an F´ JSON dictionary.

    A channel is named `<instance>.<channel>`, its deployment prefix dropped. F´ serializes
    big-endian; an enum decodes to its constant's name.

    Args:
        dictionary: the parsed F´ JSON dictionary.

    Returns:
        Channel ID to `(name, decode)`, `decode` taking the serialized bytes to the value.

    Raises:
        ValueError: naming a channel whose type is neither a primitive nor an enum.
    """
    enums = {t["qualifiedName"]: t for t in dictionary["typeDefinitions"] if t["kind"] == "enum"}
    channels: dict[int, tuple[str, Any]] = {}
    for channel in dictionary["telemetryChannels"]:
        name = channel["name"].split(".", 1)[1]
        type_name = channel["type"]["name"]
        if type_name in _PRIMITIVES:
            fmt = _PRIMITIVES[type_name]
            channels[channel["id"]] = (name, lambda raw, fmt=fmt: struct.unpack(fmt, raw)[0])
        elif type_name in enums:
            enum = enums[type_name]
            fmt = _PRIMITIVES[enum["representationType"]["name"]]
            names = {c["value"]: c["name"] for c in enum["enumeratedConstants"]}
            channels[channel["id"]] = (
                name,
                lambda raw, fmt=fmt, names=names: names[struct.unpack(fmt, raw)[0]],
            )
        else:
            raise ValueError(f"channel {channel['name']} has type {type_name}, not decoded")
    return channels


def telemetry_by_name(
    channels: Mapping[int, tuple[str, Any]], raw: Mapping[int, bytes]
) -> dict[str, Any]:
    """One call's raw telemetry, decoded and named.

    Args:
        channels: the decoder table `decoders` builds.
        raw: channel ID to serialized value, as the extension's `telemetry()` returns it.

    Returns:
        Channel name to value.
    """
    return {channels[cid][0]: channels[cid][1](value) for cid, value in raw.items()}


class FprimeModule(sysModel.SysModel):
    """Runs the WiseFsw deployment each tick: the clock set, the IMU reading sent, the schedule run.

    The deployment is the WiseFsw topology, whose content is the dead reckoner. The channel to
    estimate mapping in `estimate_datasets` is the one dead-reckoner-specific piece of this host.
    The deployment is one per process, so one module flies at a time. `Reset` boots it at t = 0
    and gives the dead reckoner its initial state, handed over directly rather than by command.
    Each `UpdateState` after the last tick reads the IMU once, steps the deployment and logs
    every channel the tick wrote, by the tick's time in ns.

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
            initial: the dead reckoner's state at t = 0: `sigma0_BN` (MRP), `r0_N` (m) and `v0_N`
                (m/s), each (3,), in the shape of a scenario's `initial_state()`.
        """
        super().__init__()
        self._imu = imu
        self._mu = float(mu)
        self._dcm_PB = np.asarray(dcm_PB, dtype=float)
        self._initial = {k: np.asarray(v, dtype=float) for k, v in initial.items()}
        dictionary = json.loads(DICTIONARY.read_text())
        self._channels = decoders(dictionary)
        self.build = {
            "host": "gnc_cdh.fprime.FprimeModule",
            "frameworkVersion": dictionary["metadata"]["frameworkVersion"],
            "projectVersion": dictionary["metadata"]["projectVersion"],
        }
        self._t_ns = 0
        self._log: dict[int, dict[str, Any]] = {}

    def Reset(self, CurrentSimNanos: int) -> None:
        """Boots the deployment, initializes the dead reckoner and logs the telemetry at t = 0.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            RuntimeError: the IMU reader is not subscribed.
        """
        from gnc_cdh.fprime import _wise_fsw

        if not self._imu.isLinked():
            raise RuntimeError("the IMU reader is not subscribed to any message")
        self._t_ns = CurrentSimNanos
        _wise_fsw.boot(mu=self._mu, dcm_PB=self._dcm_PB)
        _wise_fsw.initialize_nav(
            t_ns=self._t_ns,
            sigma_BN=self._initial["sigma0_BN"],
            r_BN_N=self._initial["r0_N"],
            v_BN_N=self._initial["v0_N"],
        )
        self._log = {self._t_ns: self._written(_wise_fsw)}

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the deployment to the current time when it lies after the last tick.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            RuntimeError: the tick is not at a whole microsecond, or the IMU reader has never
                been written.
        """
        from gnc_cdh.fprime import _wise_fsw

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
        _wise_fsw.step(
            t_ns=CurrentSimNanos,
            angVelPlatform=np.array(reading.AngVelPlatform, dtype=float),
            accelPlatform=np.array(reading.AccelPlatform, dtype=float),
        )
        self._t_ns = CurrentSimNanos
        self._log[CurrentSimNanos] = self._written(_wise_fsw)

    def _written(self, wise_fsw: Any) -> dict[str, Any]:
        """Every channel the deployment's last call wrote, decoded and named.

        Args:
            wise_fsw: the deployment's extension module.

        Returns:
            Channel name to value.
        """
        return telemetry_by_name(self._channels, wise_fsw.telemetry())

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

        The attitude quaternion becomes `sigma_BN`, the MRP whose [NB] is the quaternion's matrix.

        Args:
            t_s: (N,) s, the record times, each one a tick's time to the nanosecond.

        Returns:
            `est/sigma_BN` (MRP), `est/r_BN_N` (m) and `est/v_BN_N` (m/s), each (N, 3).

        Raises:
            KeyError: naming a record time no tick logged.
        """
        rows = []
        for t in t_s:
            t_ns = round(float(t) * _NANOSECONDS_PER_SECOND)
            if t_ns not in self._log:
                raise KeyError(f"no telemetry was logged at t = {t} s")
            rows.append(self._log[t_ns])
        quaternion = [[row[f"nav.bodyEciAttitude{a}"] for a in "XYZW"] for row in rows]
        values = {
            "sigma_BN": Rotation.from_quat(quaternion).as_mrp(),
            "r_BN_N": np.array([[row[f"nav.bodyEciPos{a}"] for a in "XYZ"] for row in rows]),
            "v_BN_N": np.array([[row[f"nav.bodyEciVel{a}"] for a in "XYZ"] for row in rows]),
        }
        return {f"est/{name}": (value, UNITS[name]) for name, value in values.items()}
