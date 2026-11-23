"""The Python build's ground link: the commands the ground uplinks and the telemetry it drains.

As the F´ build's `Cdh.GroundLink` stands in for its comm stack, this holds the queue of commands
uplinked since the last tick, their responses and every raw telemetry write, each tagged with the
tick it was written at. CDH runs the queue through `cdh.commands` and logs what each algorithm wrote
through `cdh.telemetry`; the frame runner packs the values with the dictionary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from fsw.python.cdh import commands, telemetry

__all__ = ["GroundLink"]


class GroundLink:
    """The ground's commands into, and the raw telemetry out of, one boot of the Python build."""

    def __init__(self, handlers: commands.Handlers) -> None:
        """Starts with nothing uplinked, answered or written.

        Args:
            handlers: each command's handler, as `cdh.commands.handlers` gives them.
        """
        self._handlers = handlers
        self._uplinked: list[tuple[str, Mapping[str, Any], int]] = []
        self._responses: list[tuple[int, str, str | None]] = []
        self._frame: dict[str, Any] = {}
        self._times: dict[str, list[int]] = {}
        self._values: dict[str, list[Any]] = {}

    def run_commands(self, t_ns: int) -> None:
        """Runs every command uplinked since the last call, logging what each handler wrote.

        Args:
            t_ns: ns, the tick's time, which tags the writes.
        """
        queued, self._uplinked = self._uplinked, []
        for name, args, context in queued:
            dispatched = commands.dispatch(self._handlers, name, args, t_ns)
            self._responses.append((context, dispatched.response, dispatched.reason))
            self._frame.update((channel, value) for channel, _, value in dispatched.writes)

    def log(self, instance: str, written: NamedTuple | None, t_ns: int) -> None:
        """Logs an algorithm's telemetry tuple, a write per field written.

        Args:
            instance: the algorithm's instance's unqualified name.
            written: its `<Name>Telemetry` tuple, or `None`.
            t_ns: ns, the tick's time, which tags the writes.
        """
        self._frame.update((channel, value) for channel, _, value in telemetry.writes(instance, written, t_ns))

    def send(self, t_ns: int) -> None:
        """Downlinks each channel's latest write of the frame, as F´'s telemetry database does.

        Args:
            t_ns: ns, the frame's time, which tags each value.
        """
        for channel, value in self._frame.items():
            if channel not in self._times:
                self._times[channel], self._values[channel] = [], []
            self._times[channel].append(t_ns)
            self._values[channel].append(value)
        self._frame.clear()

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
            message of the `Refused` a handler refused it with, else `None`.
        """
        drained, self._responses = self._responses, []
        return drained

    def telemetry(self) -> dict[str, tuple[list[int], list[Any]]]:
        """Every value downlinked since the last call.

        Returns:
            For each channel downlinked, `<instance>.<channel>` to its time tags in ns and its
            values as the algorithm wrote them, oldest first.
        """
        drained = {channel: (self._times[channel], self._values[channel]) for channel in self._times}
        self._times, self._values = {}, {}
        return drained
