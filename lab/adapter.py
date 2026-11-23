"""The lab adapter: a configuration's F´ deployment as a WiseDynamics FSW build, on bus bytes.

Lab equipment, as a hardware-in-the-loop rig is: it powers the deployment on, writes each sensor's
reading into the bus driver's receive buffer as the bytes the vehicle's bus would carry, reads the
bytes the deployment sends each actuator out of its transmit buffer into its Basilisk message, and
carries the bytes of the deployment's radio link, which the ground decodes. Every buffer, payload
and copy is made at boot or at the first tick; a tick after only copies.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from fsw.codegen.deployment import CONTRACT, Contract, bus_port, configuration_model, tick_period
from fsw.codegen.dictionary import Dictionary
from fsw.codegen.roles import Role, taken
from fsw.payloads import payload_type
from ground import parameters
from lab.bus_emulator import from_bus, size, to_bus
from lab.power_cycle import dictionary_path, power_cycle, source

if TYPE_CHECKING:
    from lab.fsw_extension import FswExtension

__all__ = ["Adapter"]

_NANOSECONDS_PER_MICROSECOND = 1_000

_NO_COMMANDS: Mapping[str, Any] = MappingProxyType({})
"""A tick's commands when its GNC sent none."""


class Adapter:
    """A configuration's F´ deployment, which WiseDynamics' `FswHost` hosts, on its bus bytes.

    `boot` power-cycles it: a fresh copy of the configuration's extension, booted at t = 0 with
    every component idle and PrmDb loading the case's `.dat`, so a case keeps nothing of an earlier
    one. It makes LabBusDriver's receive buffer on the port the deployment wires to each sensor
    role's CDH `<role>In`, and its transmit buffer on the port wired from each actuator role's CDH
    `<role>Out`, each its bus struct's size, and each actuator role's payload. `tick` writes each
    sensor role's message into its receive buffer, as the bus emulator writes it, then steps the
    copy: the clock is set, the uplinked commands run, the buffers are pushed and the rate groups
    tick. It reads each transmit buffer the step wrote into its role's payload, as the bus emulator
    reads it. The radio link is the copy's pins, in bytes: `uplink`, `responses` and `telemetry`
    reach the loaded copy. `ground.fprime_station.FprimeStation` is the ground's codec for them.

    Attributes:
        period_s: s, the base tick's period, the configuration's FPP constant `tickPeriod`.
        dictionary: the dictionary the configuration's build generated.
        build: the build's identity, recorded in a flight's `flight.json`: the adapter, F´'s
            version and the commit the deployment was built from.
    """

    period_s: float
    dictionary: Dictionary
    build: dict[str, str]
    _fsw: "FswExtension"
    """The copy the last `boot` powered on; unset before the first."""
    _receive: dict[str, memoryview]
    """Each sensor role's receive buffer in the copy."""
    _outputs: tuple[tuple[int, Callable[[], None], str, Any], ...]
    """Each actuator role's port bit, the copy from its transmit buffer into its payload, the role
    and the payload."""
    _commands: dict[int, Mapping[str, Any]]
    """Each set of written port bits' commands, by role, made on its first tick."""
    _bound: Mapping[str, Any] | None
    """The messages the copies into the receive buffers read; None until the first tick."""
    _inputs: tuple[Callable[[], None], ...]
    """Each sensor role's copy of its message into its receive buffer."""

    def __init__(self, configuration: str, prm_path: Path, *, contract: Contract = CONTRACT) -> None:
        """Makes the case's `.dat` beside its record, once `source` has checked the build.

        A deployment not built, or rebuilt since this process first checked it, raises as `source`
        does, and a record F´'s tool refuses raises as `ground.parameters.dat` does.

        Args:
            configuration: the configuration, the name of its GNC sub-topology in the contract.
            prm_path: the case's parameter record, JSON, which `boot` boots the deployment with.
            contract: the contract holding the configuration, the repository's by default.
        """
        source(configuration)
        self._configuration = configuration
        roles = taken(configuration_model(configuration, contract=contract), configuration)
        self._sensors: list[tuple[Role, int]] = [
            (role, bus_port(configuration, role.input, contract=contract)) for role in roles if role.sensor
        ]
        self._actuators: list[tuple[Role, int]] = [
            (role, bus_port(configuration, role.output, contract=contract)) for role in roles if not role.sensor
        ]
        self._dat = parameters.dat(prm_path, dictionary_path(configuration))
        self.period_s = tick_period(configuration, contract=contract)
        self.dictionary = Dictionary(dictionary_path(configuration))
        self.build = {
            "host": "lab.Adapter",
            "frameworkVersion": self.dictionary.metadata["frameworkVersion"],
            "projectVersion": self.dictionary.metadata["projectVersion"],
        }

    def boot(self) -> None:
        """Power-cycles the deployment: a fresh copy, booted with every component idle, its buffers made.

        An extension rebuilt after this process loaded it raises as `source` does. From the copy's
        `boot`, a `.dat` path longer than F´'s file names hold raises `ValueError`, and a parameter
        the `.dat` leaves invalid raises `RuntimeError`, naming each.
        """
        fsw = power_cycle(self._configuration)
        fsw.boot(str(self._dat.resolve()), sorted(self.dictionary.parameters_by_id))
        self._receive = {role.role: fsw.receive_buffer(port, size(role.bus)) for role, port in self._sensors}
        outputs = []
        for role, port in self._actuators:
            payload = payload_type(role.bus)()
            transmit = fsw.transmit_buffer(port, size(role.bus))
            outputs.append((1 << port, from_bus(transmit, payload), role.role, payload))
        self._outputs = tuple(outputs)
        self._commands = {}
        self._bound = None
        self._inputs = ()
        self._fsw = fsw

    def tick(self, t_ns: int, messages_by_role: Mapping[str, Any]) -> Mapping[str, Any]:
        """Steps the deployment on each role's message.

        The messages are bound to the receive buffers at the first tick, and again at a tick given
        another mapping; a tick given the same mapping copies its payloads as they stand. A binding
        tick refuses a sensor role with no message with `KeyError`, and one whose message is of
        another class than its bus struct mirrors with `TypeError`, naming each.

        Args:
            t_ns: ns, the tick's time.
            messages_by_role: each role's Basilisk message payload, a live view of its message, as
                `FswHost` gives it, the same mapping every tick.

        Returns:
            The actuator commands, by role: for each actuator role whose transmit buffer the step's
            GNC wrote, its payload, holding the last command sent. Each role's payload is the same
            object every tick, so copy what you keep.

        Raises:
            RuntimeError: the tick is not at a whole microsecond, which F´'s clock cannot hold.
        """
        if t_ns % _NANOSECONDS_PER_MICROSECOND:
            raise RuntimeError(
                f"the tick at {t_ns} ns is not a whole microsecond, which the deployment's clock cannot hold"
            )
        if messages_by_role is not self._bound:
            self._bind(messages_by_role)
        for copy in self._inputs:
            copy()
        written = self._fsw.step(t_ns)
        if not written:
            return _NO_COMMANDS
        for bit, copy, _, _ in self._outputs:
            if bit & written:
                copy()
        if written not in self._commands:
            self._commands[written] = MappingProxyType(
                {role: payload for bit, _, role, payload in self._outputs if bit & written}
            )
        return self._commands[written]

    def _bind(self, messages_by_role: Mapping[str, Any]) -> None:
        """Binds each sensor role's message to its receive buffer.

        Args:
            messages_by_role: each role's Basilisk message payload.

        Raises:
            KeyError: a sensor role the configuration takes has no message, naming it.
            TypeError: a role's message is of another class than its bus struct mirrors, naming both.
        """
        for role, _ in self._sensors:
            if role.role not in messages_by_role:
                raise KeyError(
                    f"the configuration takes the role {role.role}, which the vehicle's messages"
                    f" {sorted(messages_by_role)} lack"
                )
            given, wanted = type(messages_by_role[role.role]).__name__, payload_type(role.bus).__name__
            if given != wanted:
                raise TypeError(f"the role {role.role}'s message is a {given}, but its bus struct mirrors {wanted}")
        self._inputs = tuple(to_bus(messages_by_role[role.role], self._receive[role.role]) for role, _ in self._sensors)
        self._bound = messages_by_role

    def uplink(self, packet: bytes, context: int) -> None:
        """Queues an F´ command packet at the loaded copy's dispatcher; the next tick runs it.

        Args:
            packet: the command packet, as F´ frames it.
            context: the ground's number for the command, returned with its response.
        """
        self._fsw.uplink(packet, context)

    def responses(self) -> list[tuple[int, int]]:
        """The loaded copy's command responses since the last call, oldest first.

        Returns:
            `(context, Fw.CmdResponse value)`.
        """
        return self._fsw.responses()

    def telemetry(self) -> list[tuple[int, int, bytes]]:
        """The loaded copy's telemetry writes since the last call, oldest first.

        Returns:
            `(channel ID, F´ time tag in ns, serialized value)`.
        """
        return self._fsw.telemetry()
