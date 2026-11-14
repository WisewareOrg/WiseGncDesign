"""The Python build: one frame per base tick, through its partitions, as a WiseDynamics FSW build.

Each tick is one frame (ADR 0005 rev 1): CDH-in dispatches the commands uplinked since the last
tick, RIO-in reads each paired role's message as its bus struct, CDH-in converts it to its GNC
input, GNC runs the rate groups the base tick fires, CDH-out logs every telemetry write tagged with
the tick's time, and RIO-out returns the actuator commands. The configuration's FPP gives all of
it: the GNC sub-topology's wiring and rates, the pairing, the dictionary and the base tick.
"""

import functools
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from fsw.codegen import fpp_types
from fsw.codegen.deployment import configuration_model, tick_period
from fsw.python.cdh import commands, inputs, parameters, telemetry
from fsw.python.gnc.partition import GncPartition
from fsw.python.platform.rates import RateGroupDriver, dividers
from fsw.python.rio import messages
from ground.dictionary import Dictionary

__all__ = ["FrameRunner"]

_NANOSECONDS_PER_SECOND = 1e9


class FrameRunner:
    """A configuration's Python build, which WiseDynamics' `FswHost` hosts, on the radio edge.

    `boot` power-cycles it: every algorithm is built afresh on its parameters, read from the case's
    record by CDH. `tick` runs one frame. The ground reaches it by name: `uplink` queues a command,
    which the next tick runs before the GNC, and `responses` and `telemetry` drain what came back.

    Attributes:
        period_s: s, the base tick's period, the configuration's FPP constant `tickPeriod`.
        dictionary: the configuration's dictionary, generated from its GNC sub-topology.
        build: the build's identity, recorded in a flight's `flight.json`.
    """

    period_s: float
    dictionary: Dictionary
    build = {"host": "fsw.python.FrameRunner"}

    def __init__(self, configuration: str, prm_path: Path, components: Sequence[type]) -> None:
        """Reads the configuration's FPP and matches each algorithm's class to its component.

        Args:
            configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`,
                such as `ImuDeadReckoning`.
            prm_path: the case's parameter record, which `boot` reads.
            components: the algorithms' classes, each named as its FPP component.
        """
        model = configuration_model(configuration)
        self._gnc = GncPartition(model, configuration, components)
        self._pairs = inputs.pairings(model, configuration)
        self._dividers = dividers(model, self._gnc.rate_groups)
        self._prm_path = Path(prm_path)
        self.period_s = tick_period(configuration)
        self.dictionary = Dictionary.from_sub_topology(configuration)
        self._uplinked: list[tuple[str, Mapping[str, Any], int]] = []
        self._responses: list[tuple[int, str, str | None]] = []
        self._log: list[tuple[str, int, Any]] = []

    def boot(self) -> None:
        """Builds every algorithm afresh on the case's parameters, with the tick count at 0."""
        self._gnc.boot(
            {
                name: parameters.read(
                    self._prm_path,
                    functools.reduce(getattr, f"{component}Parameters".split("."), fpp_types),
                )
                for name, component in self._gnc.components.items()
            }
        )
        self._handlers = commands.handlers(self.dictionary, self._gnc.algorithms)
        self._driver = RateGroupDriver(self._dividers)
        self._uplinked, self._responses, self._log = [], [], []

    def tick(self, t_ns: int, messages_by_role: Mapping[str, Any]) -> dict[str, Any]:
        """Runs one frame.

        Args:
            t_ns: ns, the tick's time.
            messages_by_role: each role's Basilisk message payload, valid during this call only.

        Returns:
            The actuator commands, by role.
        """
        queued, self._uplinked = self._uplinked, []
        for name, args, context in queued:
            response, reason, writes = commands.dispatch(self._handlers, name, args)
            self._responses.append((context, response, reason))
            self._log.extend((channel, t_ns, value) for channel, value in writes)
        read = messages.read(self._pairs, messages_by_role)
        for port, value in inputs.convert(self._pairs, read).items():
            self._gnc.write(port, value)
        t = t_ns / _NANOSECONDS_PER_SECOND
        for instance, written in self._gnc.run(t, self._driver.tick()):
            self._log.extend(
                (channel, t_ns, value) for channel, value in telemetry.writes(instance, written)
            )
        return messages.commands()

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
