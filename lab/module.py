"""A Basilisk Python `SysModel` running the WiseFsw F´ deployment in the simulation's process."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from fsw.python import AlgorithmModule
from ground import parameters
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab.power_cycle import power_cycle, source

__all__ = ["DICTIONARY", "FprimeModule"]

_NANOSECONDS_PER_SECOND = 1e9
_NANOSECONDS_PER_MICROSECOND = 1_000

DICTIONARY = Path(__file__).with_name("WiseFswTopologyDictionary.json")
"""The dictionary F´ generated for the deployment, copied here by `just fsw`."""


class FprimeModule(sysModel.SysModel):
    """Runs the WiseFsw deployment each tick, and presents the ground's radio edge to it.

    `Reset` power-cycles the deployment: it loads a fresh copy and boots it at t = 0 with the dead
    reckoner idle and PrmDb loading the case's `.dat`, so a case keeps nothing of an earlier one.
    Each `UpdateState` whose time lies after the last tick's sets the clock, runs the uplinked
    commands through F´'s command dispatcher, sends the IMU reading and ticks the rate groups. The
    radio edge is an `FprimeStation` on the copy's pins: it encodes each command into F´'s packet,
    and the responses and every telemetry write, each with its F´ time tag, come down through it.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in, the Python
            host's, so the two builds fly at one rate.
        dictionary: the deployment's dictionary.
        failure: the exception `Reset` or a tick raised, kept whole, else `None`.
        build: the host's build identity, recorded in a flight's `flight.json`: the host, F´'s
            version and the commit the deployment was built from.
    """

    period_s = AlgorithmModule.period_s
    dictionary: Dictionary
    failure: BaseException | None
    build: dict[str, str]
    _fsw: ModuleType
    """The copy of the deployment the last `Reset` loaded; unset before the first."""
    _station: FprimeStation
    """The radio edge on that copy; unset before the first `Reset`."""

    def __init__(self, imu: Any, prm_path: Path) -> None:
        """Makes the case's `.dat` beside its record, once `source` has checked the build.

        A deployment not built, or rebuilt since this process first checked it, raises as `source`
        does, and a record F´'s tool refuses raises as `ground.parameters.dat` does.

        Args:
            imu: the IMU reader, subscribed by the caller.
            prm_path: the case's parameter record, JSON, which `Reset` boots the deployment with.
        """
        super().__init__()
        source()
        self._imu = imu
        self._dat = parameters.dat(prm_path, DICTIONARY)
        self.dictionary = Dictionary(DICTIONARY)
        self.failure = None
        self.build = {
            "host": "lab.FprimeModule",
            "frameworkVersion": self.dictionary.metadata["frameworkVersion"],
            "projectVersion": self.dictionary.metadata["projectVersion"],
        }
        self._t_ns = 0

    def uplink(self, name: str, args: Mapping[str, Any], context: int) -> None:
        """Queues a command at F´'s dispatcher, through the station, which runs it at the next tick.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name, as `Dictionary.arguments` types them.
            context: the ground's number for the command, returned with its response.
        """
        self._station.uplink(name, args, context)

    def responses(self) -> list[tuple[int, str, str | None]]:
        """The command responses since the last call, oldest first.

        Returns:
            As `FprimeStation.responses` gives them: F´ gives no reason.
        """
        return self._station.responses()

    def telemetry(self) -> list[tuple[str, int, bytes]]:
        """Every telemetry write since the last call, in the order written.

        Returns:
            As `FprimeStation.telemetry` gives them, each value serialized as F´ writes it.
        """
        return self._station.telemetry()

    def values(self, name: str, raws: Sequence[bytes]) -> np.ndarray:
        """The values F´ wrote to one channel, decoded in one batch by the station.

        Args:
            name: `<instance>.<channel>`.
            raws: its writes' bytes, as `telemetry` gave them.

        Returns:
            As `FprimeStation.values` gives them.
        """
        return self._station.values(name, raws)

    def Reset(self, CurrentSimNanos: int) -> None:
        """Power-cycles the deployment: a fresh copy, booted with the dead reckoner idle.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            RuntimeError: naming an extension rebuilt after this process loaded it, an IMU reader
                that is not subscribed, or each parameter the `.dat` leaves invalid.
            BaseException: the reset's exception, kept whole in `failure`.
        """
        try:
            self._fsw = power_cycle()
            self._station = FprimeStation(self._fsw, self.dictionary)
            if not self._imu.isLinked():
                raise RuntimeError("the IMU reader is not subscribed to any message")
            self._t_ns = CurrentSimNanos
            self._fsw.boot(str(self._dat.resolve()), sorted(self.dictionary.parameters_by_id))
        except BaseException as error:
            self.failure = error
            raise

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the deployment on the IMU's reading, when the time lies after the last tick.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            RuntimeError: the tick is not at a whole microsecond, or the IMU reader has never
                been written, kept whole in `failure`.
            BaseException: the tick's exception, kept whole in `failure`.
        """
        if not CurrentSimNanos > self._t_ns:
            return
        try:
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
        except BaseException as error:
            self.failure = error
            raise
