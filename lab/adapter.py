"""The lab adapter: a configuration's F´ deployment as a WiseDynamics FSW build, on bus bytes.

Lab equipment, as a hardware-in-the-loop rig is: it powers the deployment on, pushes each sensor's
reading onto the bus as the bytes the vehicle's bus would carry, turns the bytes the deployment
sends each actuator back into its Basilisk message, and carries the bytes of the deployment's radio
link, which the ground decodes.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fsw.codegen.deployment import CONTRACT, Contract, bus_port, configuration_model, tick_period
from fsw.codegen.dictionary import Dictionary
from fsw.codegen.roles import Role, taken
from ground import parameters
from lab.bus_emulator import deserialize, serialize
from lab.power_cycle import dictionary_path, power_cycle, source

if TYPE_CHECKING:
    from lab.fsw_extension import FswExtension

__all__ = ["Adapter"]

_NANOSECONDS_PER_MICROSECOND = 1_000


class Adapter:
    """A configuration's F´ deployment, which WiseDynamics' `FswHost` hosts, on its bus bytes.

    `boot` power-cycles it: a fresh copy of the configuration's extension, booted at t = 0 with
    every component idle and PrmDb loading the case's `.dat`, so a case keeps nothing of an earlier
    one. `tick` sets the clock, runs the uplinked commands, pushes each sensor role's message, as
    the bus emulator writes it, on the LabBusDriver port the deployment wires to the CDH's
    `<role>In`, ticks the rate groups, and returns the bytes the CDH's `<role>Out` sent each
    actuator role's LabBusDriver port, as the bus emulator reads them back. The radio link is the
    copy's pins, in bytes: `uplink`, `responses` and `telemetry` reach the loaded copy.
    `ground.fprime_station.FprimeStation` is the ground's codec for them.

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
        self._ports = {
            role.role: bus_port(configuration, role.input, contract=contract) for role in roles if role.sensor
        }
        self._actuators: dict[int, Role] = {
            bus_port(configuration, role.output, contract=contract): role for role in roles if not role.sensor
        }
        self._dat = parameters.dat(prm_path, dictionary_path(configuration))
        self.period_s = tick_period(configuration, contract=contract)
        self.dictionary = Dictionary(dictionary_path(configuration))
        self.build = {
            "host": "lab.Adapter",
            "frameworkVersion": self.dictionary.metadata["frameworkVersion"],
            "projectVersion": self.dictionary.metadata["projectVersion"],
        }

    def boot(self) -> None:
        """Power-cycles the deployment: a fresh copy, booted with every component idle.

        An extension rebuilt after this process loaded it raises as `source` does. From the copy's
        `boot`, a `.dat` path longer than F´'s file names hold raises `ValueError`, and a parameter
        the `.dat` leaves invalid raises `RuntimeError`, naming each.
        """
        self._fsw = power_cycle(self._configuration)
        self._fsw.boot(str(self._dat.resolve()), sorted(self.dictionary.parameters_by_id))

    def tick(self, t_ns: int, messages_by_role: Mapping[str, Any]) -> dict[str, Any]:
        """Steps the deployment on each role's message.

        Args:
            t_ns: ns, the tick's time.
            messages_by_role: each role's Basilisk message payload, valid during this call only.

        Returns:
            The actuator commands, by role: for each actuator role whose bytes the step's GNC sent,
            a fresh `messaging.<Name>Payload`, the last sent when sent more than once.

        Raises:
            RuntimeError: the tick is not at a whole microsecond, which F´'s clock cannot hold.
            KeyError: a sensor role the configuration takes has no message, naming it.
        """
        if t_ns % _NANOSECONDS_PER_MICROSECOND:
            raise RuntimeError(
                f"the tick at {t_ns} ns is not a whole microsecond, which the deployment's clock cannot hold"
            )
        bus = []
        for role, port in self._ports.items():
            if role not in messages_by_role:
                raise KeyError(
                    f"the configuration takes the role {role}, which the vehicle's messages"
                    f" {sorted(messages_by_role)} lack"
                )
            bus.append((port, serialize(messages_by_role[role])))
        sent = self._fsw.step(t_ns=t_ns, bus=bus)
        commands = {}
        for port, data in sent:
            role = self._actuators[port]
            commands[role.role] = deserialize(role.bus, data)
        return commands

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
