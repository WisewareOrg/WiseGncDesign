"""The roles of `Cdh.BusConverter`: each role's bus struct, paired with the GNC's struct.

`Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp` pairs each role, as its annotation states: an
input `<role>In` and an output `<role>Out`, exactly one of them carrying a bus struct. A sensor's
input carries the bus struct and its output the GNC's; an actuator's the reverse. Both builds' CDH
read the pairing here: the F´ build's generator, `fsw.codegen.bus_converter`, and the Python
build's `fsw.python.cdh`.
"""

from typing import NamedTuple

from fsw.codegen.fpp_model import Model, Port
from fsw.codegen.members import DRIVER

__all__ = ["CONVERTER", "Role", "roles", "taken"]

CONVERTER = "Cdh.BusConverter"
"""The component whose port pairs are the roles."""


class Role(NamedTuple):
    """A role's pair of `Cdh.BusConverter` ports.

    Attributes:
        role: the role, such as `imu`.
        bus: the bus struct's qualified FPP name, such as `Bus.ImuSensorMsg`.
        icd: the GNC struct's qualified FPP name, such as `Gnc.ImuReading`.
        input: the input port's name, `<role>In`.
        output: the output port's name, `<role>Out`.
        sensor: whether the role is a sensor, bus struct to GNC struct, rather than an actuator,
            GNC struct to bus struct.
    """

    role: str
    bus: str
    icd: str
    input: str
    output: str
    sensor: bool


def _carried(port: Port) -> str:
    """The struct a port carries: its one argument's type.

    Args:
        port: the port.

    Returns:
        The struct's qualified name.
    """
    [argument] = port.args
    return argument.type


def roles(model: Model) -> list[Role]:
    """Every role of `Cdh.BusConverter`: each input `<role>In`, with its output `<role>Out`.

    Args:
        model: the model holding the converter.

    Returns:
        The roles, in the converter's input port order.

    Raises:
        ValueError: a role has no `<role>Out`, or both or neither of its ports carry a bus struct,
            naming the role.
    """
    converter = model.components[CONVERTER]
    outputs = {port.name: port for port in converter.outputs}
    found = []
    for port in converter.inputs:
        role = port.name.removesuffix("In")
        output = outputs.get(f"{role}Out")
        if output is None:
            raise ValueError(f"{CONVERTER}'s role {role} has {port.name} but no {role}Out")
        carried_in, carried_out = _carried(port), _carried(output)
        if carried_in.startswith("Bus.") == carried_out.startswith("Bus."):
            carried = "both carry" if carried_in.startswith("Bus.") else "neither carries"
            raise ValueError(
                f"{CONVERTER}'s role {role}'s {port.name} and {output.name} {carried} a bus"
                " struct, so the role has no direction"
            )
        sensor = carried_in.startswith("Bus.")
        bus, icd = (carried_in, carried_out) if sensor else (carried_out, carried_in)
        found.append(Role(role, bus, icd, port.name, output.name, sensor))
    return found


def taken(model: Model, configuration: str) -> tuple[Role, ...]:
    """The roles a configuration takes: those its GNC sub-topology's own ports expose.

    The sub-topology is `<configuration>.Gnc`. A sensor role is taken at a topology port
    `<role>In` on an instance's input port, and an actuator role at a topology port `<role>Out` on
    an instance's output port. The rate group driver's port is not a role's.

    Args:
        model: the model holding the converter and the sub-topology.
        configuration: the configuration, the name of its GNC sub-topology.

    Returns:
        The roles, in the converter's order.

    Raises:
        ValueError: a topology port names no role in the direction of the instance port it
            exposes, naming it; or as `roles` raises.
    """
    topology = f"{configuration}.Gnc"
    declared = roles(model)
    exposed = set()
    for name, port in model.ports.items():
        if not name.startswith(f"{topology}."):
            continue
        component = model.components[model.instances[port.instance].component]
        if component.name == DRIVER:
            continue
        short = name.removeprefix(f"{topology}.")
        sensor = port.port in {p.name for p in component.inputs}
        if not any(_exposed_at(role) == (short, sensor) for role in declared):
            kind, end = ("sensor", "input") if sensor else ("actuator", "output")
            raise ValueError(
                f"{topology}'s port {short}, an instance's {end}, names no {kind} role of"
                f" {CONVERTER}"
            )
        exposed.add((short, sensor))
    return tuple(role for role in declared if _exposed_at(role) in exposed)


def _exposed_at(role: Role) -> tuple[str, bool]:
    """Where a configuration takes a role: its sub-topology port's name, and the role's direction.

    Args:
        role: the role.

    Returns:
        `(<role>In, True)` for a sensor, `(<role>Out, False)` for an actuator.
    """
    return (role.input, True) if role.sensor else (role.output, False)
