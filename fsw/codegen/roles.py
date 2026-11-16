"""The roles of `Cdh.BusConverter`: each sensor role's bus struct, paired with the GNC's struct.

`Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp` pairs each role, as its annotation states: a
bus-typed input `<role>In` and an output `<role>Out` of the GNC's struct. Both builds' CDH read the
pairing here: the F´ build's generator, `fsw.codegen.bus_converter`, and the Python build's
`fsw.python.cdh.inputs`.
"""

from typing import NamedTuple

from fsw.codegen.fpp_model import Model, Port

__all__ = ["CONVERTER", "Role", "roles"]

CONVERTER = "Cdh.BusConverter"
"""The component whose port pairs are the roles."""


class Role(NamedTuple):
    """A sensor role's pair of `Cdh.BusConverter` ports.

    Attributes:
        role: the role, such as `imu`.
        bus: the bus struct's qualified FPP name, such as `Bus.ImuSensorMsg`.
        icd: the GNC struct's qualified FPP name, such as `Gnc.ImuReading`.
        input: the input port's name, `<role>In`.
        output: the output port's name, `<role>Out`.
    """

    role: str
    bus: str
    icd: str
    input: str
    output: str


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
    """Every role of `Cdh.BusConverter`: each bus-typed input, with its output.

    Args:
        model: the model holding the converter.

    Returns:
        The roles, in the converter's port order.

    Raises:
        ValueError: a role has no `<role>Out`, or a bus-typed one, naming the role.
    """
    converter = model.components[CONVERTER]
    outputs = {port.name: port for port in converter.outputs}
    found = []
    for port in converter.inputs:
        bus = _carried(port)
        if not bus.startswith("Bus."):
            continue
        role = port.name.removesuffix("In")
        output = outputs.get(f"{role}Out")
        if output is None or _carried(output).startswith("Bus."):
            raise ValueError(
                f"{CONVERTER}'s role {role} takes {bus} at {port.name} but has no {role}Out of a"
                " GNC type"
            )
        found.append(Role(role, bus, _carried(output), port.name, output.name))
    return found
