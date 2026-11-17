"""The Python build's ground link: the commands the ground uplinks and the telemetry it drains.

As the F´ build's `Sim.GroundLink` stands in for its comm stack, this holds the queue of commands
uplinked since the last tick, their responses and every raw telemetry write, each tagged with the
tick it was written at. CDH runs the queue through `cdh.commands` and logs what each algorithm wrote
through `cdh.telemetry`; the ground packs the values with the dictionary.
"""

from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

import numpy as np

from fsw.python.cdh import commands, telemetry
from ground.dictionary import Dictionary

__all__ = ["GroundLink"]


class GroundLink:
    """The ground's commands into, and the raw telemetry out of, one boot of the Python build.

    Attributes:
        dictionary: the dictionary its commands and channels are named in.
    """

    dictionary: Dictionary

    def __init__(self, dictionary: Dictionary, handlers: commands.Handlers) -> None:
        """Starts with nothing uplinked, answered or written.

        Args:
            dictionary: the configuration's dictionary.
            handlers: each command's handler, as `cdh.commands.handlers` gives them.
        """
        self.dictionary = dictionary
        self._handlers = handlers
        self._uplinked: list[tuple[str, Mapping[str, Any], int]] = []
        self._responses: list[tuple[int, str, str | None]] = []
        self._log: list[tuple[str, int, Any]] = []

    def run_commands(self, t_ns: int) -> None:
        """Runs every command uplinked since the last call, logging what each handler wrote.

        Args:
            t_ns: ns, the tick's time, which tags the writes.
        """
        queued, self._uplinked = self._uplinked, []
        for name, args, context in queued:
            dispatched = commands.dispatch(self._handlers, name, args)
            self._responses.append((context, dispatched.response, dispatched.reason))
            self._log.extend((channel, t_ns, value) for channel, value in dispatched.writes)

    def log(self, instance: str, written: NamedTuple | None, t_ns: int) -> None:
        """Logs an algorithm's telemetry tuple, a write per field written.

        Args:
            instance: the algorithm's instance's unqualified name.
            written: its `<Name>Telemetry` tuple, or `None`.
            t_ns: ns, the tick's time, which tags the writes.
        """
        self._log.extend(
            (channel, t_ns, value) for channel, value in telemetry.writes(instance, written)
        )

    def uplink(self, name: str, args: Mapping[str, Any], context: int) -> None:
        """Queues a command, which runs at the next tick.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name, as `Dictionary.arguments` types them.
            context: the ground's number for the command, returned with its response.
        """
        self._uplinked.append((name, args, context))

    def responses(self) -> list[tuple[int, str, str | None]]:
        """The command responses since the last call, oldest first.

        Returns:
            `(context, response, reason)`: the response a name of `Fw.CmdResponse`, and the
            message of the `ValueError` a handler refused it with, else `None`.
        """
        drained, self._responses = self._responses, []
        return drained

    def telemetry(self) -> list[tuple[str, int, Any]]:
        """Every telemetry write since the last call, in the order written.

        Returns:
            `(<instance>.<channel>, time tag in ns, value)`, the value as the algorithm wrote it.
        """
        drained, self._log = self._log, []
        return drained

    def values(self, name: str, raws: Sequence[Any]) -> np.ndarray:
        """The values written to one channel, packed in one batch.

        Args:
            name: `<instance>.<channel>`.
            raws: its writes' values, as `telemetry` gave them.

        Returns:
            As `Channel.pack_many` gives them.
        """
        return self.dictionary.channel(name).pack_many(raws)
