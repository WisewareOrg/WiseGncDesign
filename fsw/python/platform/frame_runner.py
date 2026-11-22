"""The Python build: one frame per base tick, through its partitions, as a WiseDynamics FSW build.

Each tick is one frame (ADR 0005 rev 1): CDH-in's ground link runs the commands uplinked since the
last tick, RIO-in reads each sensor role's message as its bus struct, CDH-in converts it to its GNC
input, GNC runs the rate groups the base tick fires, CDH-out's ground link logs every telemetry
write and CDH-out converts each actuator output GNC wrote to its bus struct, and RIO-out returns
those as the actuator commands. The configuration's FPP gives all of it: the GNC sub-topology's
wiring and rates, the roles it takes, the dictionary and the base tick. The radio edge is
CDH's `GroundLink`, which the frame runner forwards to.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from fsw.codegen import fpp_types
from fsw.codegen.deployment import CONTRACT, Contract, configuration_model, tick_period
from fsw.codegen.dictionary import Dictionary
from fsw.codegen.roles import taken
from fsw.python.cdh import commands, inputs, outputs, parameters
from fsw.python.cdh.ground_link import GroundLink
from fsw.python.gnc.partition import GncPartition
from fsw.python.platform.rates import RateGroupDriver, dividers
from fsw.python.rio import messages

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

    def __init__(
        self,
        configuration: str,
        prm_path: Path,
        components: Sequence[type],
        *,
        contract: Contract = CONTRACT,
    ) -> None:
        """Reads the configuration's FPP and matches each algorithm's class to its component.

        Args:
            configuration: the configuration, the name of its GNC sub-topology in the contract's
                directory of them.
            prm_path: the case's parameter record, which `boot` reads.
            components: the algorithms' classes, each named as its FPP component.
            contract: the contract, the repository's by default, whose tuples it loads.
        """
        fpp_types.load(contract)
        model = configuration_model(configuration, contract=contract)
        self._configuration = configuration
        self._gnc = GncPartition(model, configuration, components)
        roles = taken(model, configuration)
        self._sensors = inputs.pairings([role for role in roles if role.sensor])
        self._actuators = outputs.pairings([role for role in roles if not role.sensor])
        self._dividers = dividers(model, self._gnc.rate_groups)
        self._prm_path = Path(prm_path)
        self.period_s = tick_period(configuration, contract=contract)
        self.dictionary = Dictionary.from_sub_topology(configuration, contract=contract)
        self._link = GroundLink({})

    def boot(self) -> None:
        """Builds every algorithm afresh on the case's parameters, with the tick count at 0.

        The ground link starts afresh with it: no command, response or write survives a boot.
        """
        self._gnc.boot(
            {
                name: parameters.read(
                    self._prm_path,
                    fpp_types.named(f"{component}Parameters"),
                    f"{self._configuration}.{name}",
                )
                for name, component in self._gnc.components.items()
            }
        )
        self._link = GroundLink(commands.handlers(self.dictionary, self._gnc.algorithms))
        self._driver = RateGroupDriver(self._dividers)

    def tick(self, t_ns: int, messages_by_role: Mapping[str, Any]) -> dict[str, Any]:
        """Runs one frame.

        Args:
            t_ns: ns, the tick's time.
            messages_by_role: each role's Basilisk message payload, valid during this call only.

        Returns:
            The actuator commands, by role: each a fresh `messaging.<Name>Payload` of the message
            the role's bus struct mirrors, for each actuator output GNC wrote this frame.
        """
        self._link.run_commands(t_ns)
        read = messages.read(self._sensors, messages_by_role)
        for port, value in inputs.convert(self._sensors, read).items():
            self._gnc.write(port, value)
        t = t_ns / _NANOSECONDS_PER_SECOND
        frame = self._gnc.run(t, self._driver.tick())
        for member in frame.telemetry:
            self._link.log(member.instance, member.telemetry, t_ns)
        return messages.commands(self._actuators, outputs.convert(self._actuators, frame.outputs))

    def uplink(self, name: str, args: Mapping[str, Any], context: int) -> None:
        """Queues a command at the ground link, which runs it at the next tick.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name, as `Dictionary.arguments` types them.
            context: the ground's number for the command, returned with its response.
        """
        self._link.uplink(name, args, context)

    def responses(self) -> list[tuple[int, str, str | None]]:
        """The command responses since the last call, oldest first.

        Returns:
            As `GroundLink.responses` gives them.
        """
        return self._link.responses()

    def telemetry(self) -> list[tuple[str, int, Any]]:
        """Every telemetry write since the last call, in the order written.

        Returns:
            As `GroundLink.telemetry` gives them.
        """
        return self._link.telemetry()

    def values(self, name: str, raws: Sequence[Any]) -> np.ndarray:
        """The values written to one channel, packed in one batch.

        Args:
            name: `<instance>.<channel>`.
            raws: its writes' values, as `telemetry` gave them.

        Returns:
            As `Channel.pack_many` gives them.
        """
        return self.dictionary.channel(name).pack_many(raws)
