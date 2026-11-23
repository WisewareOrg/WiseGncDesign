"""The Python build: one frame per base tick, through its partitions, as a WiseDynamics FSW build.

Each tick is one frame (ADR 0005 rev 2): CDH-in's ground link runs the commands uplinked since the
last tick, RIO-in reads each sensor role's message as its bus struct, CDH-in converts it to its GNC
input, GNC runs the rate groups the base tick fires, CDH-out's ground link logs every telemetry
write and CDH-out converts each actuator output GNC wrote to its bus struct, and RIO-out returns
those as the actuator commands. The configuration's FPP gives all of it: the GNC sub-topology's
wiring and rates, the roles it takes, the dictionary and the base tick. The radio edge is
CDH's `GroundLink`, which the frame runner forwards to.
"""

from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from fsw.codegen import fpp_types
from fsw.codegen.deployment import CONTRACT, Contract, configuration_model, tick_period
from fsw.codegen.dictionary import Dictionary
from fsw.codegen.roles import taken
from fsw.python.cdh import commands, inputs, outputs, parameters
from fsw.python.cdh.ground_link import GroundLink
from fsw.python.cdh.telemetry import Entry
from fsw.python.gnc.partition import GncPartition
from fsw.python.platform.rates import RateGroupDriver, dividers
from fsw.python.rio import messages

__all__ = ["FrameRunner"]

_NANOSECONDS_PER_SECOND = 1e9


class _Input(NamedTuple):
    """A sensor role's path into GNC, planned once.

    Attributes:
        role: the role.
        port: the GNC sub-topology's input port it writes.
        bind: RIO-in's binding of its payload to its read.
        convert: CDH-in's converter of its bus struct.
    """

    role: str
    port: str
    bind: Callable[[Any], Callable[[], Any]]
    convert: Callable[[Any], Any]


def _cdh_in(read: Callable[[], Any], convert: Callable[[Any], Any]) -> Callable[[], Any]:
    """A bound sensor role's GNC input: RIO-in's read, converted by CDH-in when it is a new struct.

    Args:
        read: RIO-in's read of the role's payload.
        convert: CDH-in's converter of its bus struct.

    Returns:
        A function reading the payload and giving its GNC input, the same while the read gives the
        same bus struct, whose arrays the GNC input holds.
    """
    last = converted = None

    def read_converted() -> Any:
        """Reads the payload.

        Returns:
            The GNC input.
        """
        nonlocal last, converted
        bus = read()
        if bus is not last:
            last, converted = bus, convert(bus)
        return converted

    return read_converted


class _Output(NamedTuple):
    """An actuator role's path out of GNC, planned once.

    Attributes:
        role: the role.
        port: the GNC sub-topology's output port it reads.
        convert: CDH-out's converter of its ICD struct.
        write: RIO-out's writer of its payload.
    """

    role: str
    port: str
    convert: Callable[[Any], Any]
    write: Callable[[Any], Any]


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
        self._inputs = tuple(
            _Input(pair.role, pair.port, messages.reader(pair.bus), inputs.converter(pair)) for pair in self._sensors
        )
        self._outputs = tuple(
            _Output(pair.role, pair.port, outputs.converter(pair), messages.writer(pair.bus))
            for pair in outputs.pairings([role for role in roles if not role.sensor])
        )
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
        self._bound: Mapping[str, Any] | None = None
        self._reads: tuple[tuple[str, Callable[[], Any]], ...] = ()

    def tick(self, t_ns: int, messages_by_role: Mapping[str, Any]) -> dict[str, Any]:
        """Runs one frame.

        The first tick after a boot, and a tick given another mapping than the last, checks each
        sensor role's message with `fsw.python.rio.messages.check`, which raises what it refuses,
        and binds it to RIO-in; a tick given the same mapping reads its payloads as they stand.

        Args:
            t_ns: ns, the tick's time.
            messages_by_role: each role's Basilisk message payload, a live view of its message, as
                `FswHost` gives it, the same mapping every tick.

        Returns:
            The actuator commands, by role: each the role's `messaging.<Name>Payload` of the
            message its bus struct mirrors, the same object every tick, for each actuator output
            GNC wrote this frame.
        """
        if messages_by_role is not self._bound:
            messages.check(self._sensors, messages_by_role)
            self._reads = tuple(
                (port, _cdh_in(bind(messages_by_role[role]), convert)) for role, port, bind, convert in self._inputs
            )
            self._bound = messages_by_role
        self._link.run_commands(t_ns)
        for port, read in self._reads:
            self._gnc.write(port, read())
        frame = self._gnc.run(t_ns / _NANOSECONDS_PER_SECOND, self._driver.tick())
        for member in frame.telemetry:
            self._link.log(member.instance, member.telemetry, t_ns)
        written = frame.outputs
        return {role: write(convert(written[port])) for role, port, convert, write in self._outputs if port in written}

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

    def telemetry(self) -> list[Entry]:
        """Every telemetry entry since the last call, in the order written.

        Returns:
            As `GroundLink.telemetry` gives them.
        """
        return self._link.telemetry()

    def decode(
        self, downlinks: Sequence[list[Entry]], names: Collection[str] | None = None
    ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Downlinks as each channel's values, each channel packed in one batch.

        Every write is kept, in the order written.

        Args:
            downlinks: as `telemetry` gave them, oldest first.
            names: the channels to decode, `<instance>.<channel>`; every channel when `None`.

        Returns:
            For each channel downlinked, `<instance>.<channel>` to its time tags in ns as int64 and
            its values, as `Channel.pack_many` gives them, keyed in the order of first write.
        """
        merged: dict[str, tuple[list[int], list[Any]]] = {}
        for downlink in downlinks:
            for channels, t_ns, values in downlink:
                for channel, value in zip(channels, values, strict=True):
                    if value is not None and (names is None or channel in names):
                        times, written = merged.setdefault(channel, ([], []))
                        times.append(t_ns)
                        written.append(value)
        return {
            channel: (np.array(times, dtype=np.int64), self.dictionary.channel(channel).pack_many(written))
            for channel, (times, written) in merged.items()
        }
