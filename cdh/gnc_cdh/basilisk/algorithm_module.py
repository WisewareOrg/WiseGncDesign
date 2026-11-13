"""A Basilisk Python `SysModel` hosting one algorithm as an F´ component instance, on the link."""

import inspect
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from gnc_cdh.dictionary import Channel, DecodeError, Dictionary

__all__ = ["AlgorithmModule"]

_NANOSECONDS_PER_SECOND = 1e9


class AlgorithmModule(sysModel.SysModel):
    """Hosts one algorithm inside a Basilisk task, as the F´ instance `instance` would be hosted.

    Each keyword of the algorithm's `step` other than `t` is a message field, read from the one
    input reader whose message has a field of that name. Every command the dictionary gives
    `instance` is a method of the algorithm, named and parametered as in FPP.

    The ground reaches the algorithm through the link: `uplink` queues a command packet, and the
    next tick decodes it with the dictionary's types, runs its handler before the step and keeps
    the response. A handler that returns answers `OK`, and one that raises `ValueError` answers
    `VALIDATION_ERROR`; any other exception is a bug and fails the tick.

    The algorithm writes telemetry by returning `{channel: value}` from `step` and from each
    handler, as an F´ component calls `tlmWrite_<channel>`. Each entry is one write, tagged with the
    tick's time; its channel name is checked on the tick, an array is copied as written, and the
    value is held to the channel's type when `values` packs a batch. Each tick after the last
    reads every input once and calls `step(t=..., **fields)` with `t` in s; the call Basilisk makes
    at the reset time runs nothing.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in: the flight
            software runs at 1 Hz.
        dictionary: the dictionary the algorithm is held to.
        failure: the exception a tick raised, kept whole, else `None`.
    """

    period_s = 1.0
    dictionary: Dictionary
    failure: BaseException | None

    def __init__(
        self, algorithm: Any, inputs: Mapping[str, Any], *, instance: str, dictionary: Dictionary
    ) -> None:
        """Resolves the algorithm's keywords against `inputs` and its methods against `dictionary`.

        Args:
            algorithm: the algorithm.
            inputs: reader by input role, each subscribed by the caller.
            instance: the F´ instance name the algorithm plays, such as `nav`.
            dictionary: the dictionary to hold it to.

        Raises:
            ValueError: naming a `step` keyword that no input's message carries or more than one
                does, or a command the algorithm lacks or declares with other parameters.
        """
        super().__init__()
        self._algorithm = algorithm
        self._instance = instance
        self.dictionary = dictionary
        self._inputs = MappingProxyType(dict(inputs))
        keywords = [k for k in inspect.signature(algorithm.step).parameters if k != "t"]
        self._reads = tuple((self._role(keyword), keyword) for keyword in keywords)
        self._readers = tuple(self._inputs.items())
        entries = dictionary.entries(instance)
        for name, params in entries["commands"].items():
            handler = getattr(algorithm, name, None)
            found = list(inspect.signature(handler).parameters) if callable(handler) else None
            wanted = [param for param, _ in params]
            if found != wanted:
                raise ValueError(
                    f"{instance}.{name} takes {wanted}; the algorithm has "
                    f"{'no such method' if found is None else found}"
                )
        self._ids = {
            name: dictionary.channel(f"{instance}.{name}").id for name in entries["channels"]
        }
        self.failure: BaseException | None = None
        self._inputs_written = False
        self._t_ns = 0
        self._uplinked: list[tuple[bytes, int]] = []
        self._responses: list[tuple[int, int]] = []
        self._log: list[tuple[int, int, Any]] = []

    def _role(self, keyword: str) -> str:
        """The input role whose message carries the field `keyword`.

        Args:
            keyword: one of the algorithm's `step` keywords, a message field name.

        Returns:
            The role in `inputs`.

        Raises:
            ValueError: when no input's message carries it, or more than one does.
        """
        roles = [r for r, reader in self._inputs.items() if hasattr(reader.zeroMsgPayload, keyword)]
        if len(roles) != 1:
            raise ValueError(f"step's {keyword!r} is carried by {len(roles)} inputs: {roles}")
        return roles[0]

    @property
    def build(self) -> dict[str, str]:
        """The host's build identity, recorded in a flight's `flight.json`."""
        return {"host": "gnc_cdh.basilisk.AlgorithmModule"}

    @property
    def inputs(self) -> Mapping[str, Any]:
        """Reader by input role."""
        return self._inputs

    @property
    def algorithm(self) -> Any:
        """The hosted algorithm, for inspection."""
        return self._algorithm

    def uplink(self, packet: bytes, context: int) -> None:
        """Queues a command packet, which runs at the next tick.

        Args:
            packet: the serialized command packet.
            context: the ground's number for the command, returned with its response.
        """
        self._uplinked.append((packet, context))

    def responses(self) -> list[tuple[int, int]]:
        """The command responses since the last call, oldest first.

        Returns:
            `(context, response)`, the response a value of the dictionary's `Fw.CmdResponse`.
        """
        drained, self._responses = self._responses, []
        return drained

    def telemetry(self) -> list[tuple[int, int, Any]]:
        """Every telemetry write since the last call, in the order written.

        Returns:
            `(channel ID, time tag in ns, value)`, the value as the algorithm wrote it.
        """
        drained, self._log = self._log, []
        return drained

    def values(self, channel: Channel, payloads: Sequence[Any]) -> np.ndarray:
        """The values the algorithm wrote to one channel, packed in one batch.

        Args:
            channel: the channel written.
            payloads: its writes' values, as `telemetry` gave them.

        Returns:
            As `Channel.pack_many` gives them.
        """
        return channel.pack_many(payloads)

    def Reset(self, CurrentSimNanos: int) -> None:
        """Takes the reset time as the last tick.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            RuntimeError: naming any input whose reader is not subscribed, kept whole in
                `failure`.
        """
        self._t_ns = CurrentSimNanos
        unlinked = sorted(name for name, reader in self._readers if not reader.isLinked())
        try:
            if unlinked:
                raise RuntimeError(f"inputs {unlinked} are not subscribed to any message")
        except RuntimeError as error:
            self.failure = error
            raise

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Runs the queued commands, then the step, when the time lies after the last tick.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            BaseException: the tick's exception, kept whole in `failure`: naming an input never
                written, a channel the instance does not have, or whatever a handler or `step`
                raised.
        """
        if not CurrentSimNanos > self._t_ns:
            return
        try:
            self._tick(CurrentSimNanos)
        except BaseException as error:
            self.failure = error
            raise

    def _tick(self, t_ns: int) -> None:
        """Runs one tick: the queued commands, then the step.

        Args:
            t_ns: ns, the tick's time.

        Raises:
            RuntimeError: naming any input never written.
        """
        self._t_ns = t_ns
        queued, self._uplinked = self._uplinked, []
        for packet, context in queued:
            self._responses.append((context, self._dispatch(packet)))
        t = t_ns / _NANOSECONDS_PER_SECOND
        if not self._inputs_written:
            unwritten = sorted(name for name, reader in self._readers if not reader.isWritten())
            if unwritten:
                raise RuntimeError(f"inputs {unwritten} have not been written at t = {t} s")
            self._inputs_written = True
        payloads = {name: reader() for name, reader in self._readers}
        fields = {
            keyword: np.array(getattr(payloads[role], keyword), dtype=float)
            for role, keyword in self._reads
        }
        self._write(self._algorithm.step(t=t, **fields))

    def _dispatch(self, packet: bytes) -> int:
        """Decodes a command packet and runs its handler.

        Args:
            packet: the serialized command packet.

        Returns:
            The `Fw.CmdResponse` value.
        """
        responses = self.dictionary.responses
        try:
            name, args = self.dictionary.decode_command(packet, self._instance)
        except DecodeError as error:
            return responses[error.response]
        try:
            writes = getattr(self._algorithm, name)(**args)
        except ValueError:
            return responses["VALIDATION_ERROR"]
        self._write(writes)
        return responses["OK"]

    def _write(self, writes: Mapping[str, Any] | None) -> None:
        """Logs the telemetry the algorithm returned, tagged with this tick, arrays copied.

        Args:
            writes: channel name to value, or `None` for no write.

        Raises:
            ValueError: naming a channel the instance does not have.
        """
        for name, value in (writes or {}).items():
            if name not in self._ids:
                raise ValueError(f"{self._instance}.{name} is not a channel of the dictionary")
            written = value.copy() if isinstance(value, np.ndarray) else value
            self._log.append((self._ids[name], self._t_ns, written))
