"""A Basilisk Python `SysModel` running the WiseFsw F´ deployment in the simulation's process."""

import os
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from gnc_cdh.basilisk import AlgorithmModule
from gnc_cdh.dictionary import Channel, Dictionary

__all__ = ["DICTIONARY", "FprimeModule", "extension"]

_NANOSECONDS_PER_SECOND = 1e9
_NANOSECONDS_PER_MICROSECOND = 1_000

DICTIONARY = Path(__file__).with_name("WiseFswTopologyDictionary.json")
"""The dictionary F´ generated for the deployment, copied here by `just fsw`."""

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
    """Runs the WiseFsw deployment each tick, and carries the ground's link to it.

    The deployment is one per process, so one module flies at a time. `Reset` boots it at the
    reset time with the dead reckoner idle. Each `UpdateState` after the last tick sets the clock,
    runs the uplinked commands through F´'s command dispatcher, sends the IMU reading and runs the
    schedule. The link's bytes are F´'s own: command packets go up, and the responses and every
    telemetry write with its F´ time tag come down.

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

    def __init__(self, imu: Any, mu: float, dcm_PB: np.ndarray) -> None:
        """Holds what `Reset` boots the deployment with.

        Args:
            imu: the IMU reader, subscribed by the caller.
            mu: m^3/s^2, the central body's gravitational parameter.
            dcm_PB: (3, 3) the IMU's mounting [PB], v_P = [PB] v_B.
        """
        super().__init__()
        self._fsw = extension()
        self._imu = imu
        self._mu = float(mu)
        self._dcm_PB = np.asarray(dcm_PB, dtype=float)
        self.dictionary = Dictionary(DICTIONARY)
        self.failure = None
        self.build = {
            "host": "gnc_cdh.fprime.FprimeModule",
            "frameworkVersion": self.dictionary.metadata["frameworkVersion"],
            "projectVersion": self.dictionary.metadata["projectVersion"],
        }
        self._t_ns = 0

    def uplink(self, packet: bytes, context: int) -> None:
        """Queues a command packet at F´'s dispatcher, which runs it at the next tick.

        Args:
            packet: the serialized command packet.
            context: the ground's number for the command, returned with its response.
        """
        self._fsw.uplink(packet, context)

    def responses(self) -> list[tuple[int, int, str | None]]:
        """The command responses since the last call, oldest first.

        Returns:
            `(context, response, None)`: the response a value of the dictionary's
            `Fw.CmdResponse`; F´ gives no reason with it.
        """
        return [(context, response, None) for context, response in self._fsw.responses()]

    def telemetry(self) -> list[tuple[int, int, bytes]]:
        """Every telemetry write since the last call, in the order written.

        Returns:
            `(channel ID, F´ time tag in ns, value)`, the value serialized as F´ writes it.
        """
        return self._fsw.telemetry()

    def values(self, channel: Channel, payloads: Sequence[bytes]) -> np.ndarray:
        """The values F´ wrote to one channel, decoded in one batch.

        Args:
            channel: the channel written.
            payloads: its writes' serialized values, as `telemetry` gave them.

        Returns:
            As `Channel.decode_many` gives them.
        """
        return channel.decode_many(payloads)

    def Reset(self, CurrentSimNanos: int) -> None:
        """Boots the deployment: queued commands run, the link cleared, the dead reckoner idle.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            RuntimeError: naming an extension rebuilt after this process loaded it, or an IMU
                reader that is not subscribed.
            BaseException: the reset's exception, kept whole in `failure`.
        """
        try:
            self._fsw = extension()
            if not self._imu.isLinked():
                raise RuntimeError("the IMU reader is not subscribed to any message")
            self._t_ns = CurrentSimNanos
            self._fsw.boot(mu=self._mu, dcm_PB=self._dcm_PB)
        except BaseException as error:
            self.failure = error
            raise

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the deployment to the current time when it lies after the last tick.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            BaseException: the tick's exception, kept whole in `failure`: a `RuntimeError` naming
                a tick that is not at a whole microsecond, an IMU never written, or a queue F´
                could not empty.
        """
        if not CurrentSimNanos > self._t_ns:
            return
        try:
            self._tick(CurrentSimNanos)
        except BaseException as error:
            self.failure = error
            raise

    def _tick(self, t_ns: int) -> None:
        """Steps the deployment to `t_ns` on the IMU's reading.

        Args:
            t_ns: ns, the tick's time.

        Raises:
            RuntimeError: the tick is not at a whole microsecond, or the IMU reader has never
                been written.
        """
        if t_ns % _NANOSECONDS_PER_MICROSECOND:
            raise RuntimeError(
                f"the tick at {t_ns} ns is not a whole microsecond,"
                " which the deployment's clock cannot hold"
            )
        if not self._imu.isWritten():
            raise RuntimeError(
                f"the IMU has not been written at t = {t_ns / _NANOSECONDS_PER_SECOND} s"
            )
        reading = self._imu()
        self._fsw.step(
            t_ns=t_ns,
            angVelPlatform=np.array(reading.AngVelPlatform, dtype=float),
            accelPlatform=np.array(reading.AccelPlatform, dtype=float),
        )
        self._t_ns = t_ns
