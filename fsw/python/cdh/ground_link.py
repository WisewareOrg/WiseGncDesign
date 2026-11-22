"""The Python build's ground link: the commands the ground uplinks and the telemetry it drains.

As the F´ build's `Cdh.GroundLink` stands in for its comm stack, this holds the queue of commands
uplinked since the last tick, their responses and every raw telemetry write, each tagged with the
tick it was written at. CDH runs the queue through `cdh.commands` and logs what each algorithm wrote
through `cdh.telemetry`; the frame runner packs the values with the dictionary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

import numpy as np

from fsw.python.cdh import commands

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
        self._log: dict[str, tuple[list[int], list[Any]]] = {}
        self._channels: dict[tuple[str, type], tuple[str, ...]] = {}

    def run_commands(self, t_ns: int) -> None:
        """Runs every command uplinked since the last call, logging what each handler wrote.

        Args:
            t_ns: ns, the tick's time, which tags the writes.
        """
        queued, self._uplinked = self._uplinked, []
        for name, args, context in queued:
            dispatched = commands.dispatch(self._handlers, name, args)
            self._responses.append((context, dispatched.response, dispatched.reason))
            for channel, value in dispatched.writes:
                self._write(channel, t_ns, value)

    def log(self, instance: str, written: NamedTuple | None, t_ns: int) -> None:
        """Logs an algorithm's telemetry tuple, a write per field written.

        Args:
            instance: the algorithm's instance's unqualified name.
            written: its `<Name>Telemetry` tuple, or `None`.
            t_ns: ns, the tick's time, which tags the writes.
        """
        if written is None:
            return
        key = (instance, type(written))
        channels = self._channels.get(key)
        if channels is None:
            channels = tuple(f"{instance}.{field}" for field in written._fields)
            self._channels[key] = channels
        for channel, value in zip(channels, written, strict=True):
            if value is not None:
                self._write(channel, t_ns, value.copy() if isinstance(value, np.ndarray) else value)

    def _write(self, channel: str, t_ns: int, value: Any) -> None:
        """Logs one write.

        Args:
            channel: `<instance>.<channel>`.
            t_ns: ns, its tick's time.
            value: the value as written.
        """
        column = self._log.get(channel)
        if column is None:
            column = self._log[channel] = ([], [])
        column[0].append(t_ns)
        column[1].append(value)

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

    def telemetry(self) -> dict[str, tuple[np.ndarray, list[Any]]]:
        """Every telemetry write since the last call, by channel.

        Returns:
            For each written channel, `<instance>.<channel>` to its writes' time tags in ns and
            their values as the algorithm wrote them, oldest first.
        """
        drained, self._log = self._log, {}
        return {name: (np.array(t, np.int64), values) for name, (t, values) in drained.items()}
