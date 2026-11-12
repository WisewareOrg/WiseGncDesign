"""A Basilisk Python `SysModel` running the WiseFsw F´ deployment in the simulation's process."""

import json
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel
from scipy.spatial.transform import Rotation

__all__ = ["DICTIONARY", "FprimeModule", "decoders"]

_NANOSECONDS_PER_SECOND = 1e9

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


class FprimeModule(sysModel.SysModel):
    """Runs the WiseFsw deployment each tick: the clock set, the IMU reading sent, the schedule run.

    The deployment is one per process, so one module flies at a time. `Reset` boots it at t = 0
    and gives the dead reckoner its initial state; until the initNavState command exists, that
    state is handed over directly. Each `UpdateState` after the last tick reads the IMU once,
    steps the deployment and logs every channel the tick wrote.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in: 1 Hz.
    """

    period_s = 1.0

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
        self._channels = decoders(json.loads(DICTIONARY.read_text()))
        self._t = 0.0
        self._log: list[tuple[float, dict[str, Any]]] = []

    @property
    def telemetry(self) -> list[tuple[float, dict[str, Any]]]:
        """Each tick's telemetry: its time in s, and each channel it wrote by name."""
        return self._log

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
        self._t = CurrentSimNanos / _NANOSECONDS_PER_SECOND
        _wise_fsw.boot(mu=self._mu, dcm_PB=self._dcm_PB)
        _wise_fsw.initialize_nav(
            t=self._t,
            sigma_BN=self._initial["sigma0_BN"],
            r_BN_N=self._initial["r0_N"],
            v_BN_N=self._initial["v0_N"],
        )
        self._log = [(self._t, self._latest(_wise_fsw))]

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the deployment to the current time when it lies after the last tick.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            RuntimeError: the IMU reader has never been written.
        """
        from gnc_cdh.fprime import _wise_fsw

        t = CurrentSimNanos / _NANOSECONDS_PER_SECOND
        if not t > self._t:
            return
        if not self._imu.isWritten():
            raise RuntimeError(f"the IMU has not been written at t = {t} s")
        reading = self._imu()
        _wise_fsw.step(
            t=t,
            angVelPlatform=np.array(reading.AngVelPlatform, dtype=float),
            accelPlatform=np.array(reading.AccelPlatform, dtype=float),
        )
        self._t = t
        self._log.append((t, self._latest(_wise_fsw)))

    def _latest(self, wise_fsw: Any) -> dict[str, Any]:
        """Every channel written at the current tick, decoded and named.

        Args:
            wise_fsw: the deployment's extension module.

        Returns:
            Channel name to value.
        """
        return {
            self._channels[cid][0]: self._channels[cid][1](raw)
            for cid, (time, raw) in wise_fsw.telemetry().items()
            if time == self._t
        }

    def estimate_datasets(self, t_s: np.ndarray) -> dict[str, tuple[np.ndarray, str]]:
        """The estimate's run-file datasets at the record times, from the logged telemetry.

        The attitude quaternion becomes `sigma_BN`, the MRP whose [NB] is the quaternion's matrix.

        Args:
            t_s: (N,) s, the record times, each one a tick's time.

        Returns:
            `est/sigma_BN` (MRP), `est/r_BN_N` (m) and `est/v_BN_N` (m/s), each (N, 3).

        Raises:
            KeyError: naming a record time no tick logged.
        """
        by_time = dict(self._log)
        rows = []
        for t in t_s:
            if float(t) not in by_time:
                raise KeyError(f"no telemetry was logged at t = {t} s")
            rows.append(by_time[float(t)])
        quaternion = [[row[f"nav.bodyEciAttitude{a}"] for a in "XYZW"] for row in rows]
        return {
            "est/sigma_BN": (Rotation.from_quat(quaternion).as_mrp(), "MRP"),
            "est/r_BN_N": (
                np.array([[row[f"nav.bodyEciPos{a}"] for a in "XYZ"] for row in rows]),
                "m",
            ),
            "est/v_BN_N": (
                np.array([[row[f"nav.bodyEciVel{a}"] for a in "XYZ"] for row in rows]),
                "m/s",
            ),
        }
