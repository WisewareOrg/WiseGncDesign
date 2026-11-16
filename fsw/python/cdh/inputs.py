"""The Python build's CDH-in: each sensor role's bus struct, converted to its GNC input's FPP type.

The pairing is FPP's, `Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp`, whose annotation states
its rule; a `Pair` names one role's. The bus struct is converted to the ICD struct field by field
with `fsw.codegen.fpp_types.converter`, every array a fresh copy.
"""

import functools
from collections.abc import Collection, Mapping, Sequence
from typing import Any, NamedTuple

from fsw.codegen import fpp_types
from fsw.codegen.fpp_model import Model, Port

__all__ = ["Pair", "convert", "pairings"]

_CONVERTER = "Cdh.BusConverter"
"""The component whose port pairs are the pairing."""


class Pair(NamedTuple):
    """A role's message, from its bus struct to the ICD struct its GNC port takes.

    Attributes:
        role: the vehicle's role, such as `imu`.
        bus: the bus struct's tuple, mirroring the role's Basilisk message.
        icd: the ICD struct's tuple, which the GNC port takes.
        port: the GNC sub-topology's port, such as `imuIn`.
    """

    role: str
    bus: type
    icd: type
    port: str


def _carried(port: Port) -> str:
    """The struct a port carries: its one argument's type.

    Args:
        port: the port.

    Returns:
        The struct's qualified name.
    """
    [argument] = port.args
    return argument.type


def pairings(model: Model, ports: Collection[str]) -> list[Pair]:
    """Every role a GNC sub-topology takes, paired by `Cdh.BusConverter` to its port.

    A bus-typed `<role>In` of the converter needs a `<role>Out` that is not bus-typed; a role whose
    port the sub-topology lacks is not taken, and every port it has must be a role's.

    Args:
        model: the model holding the converter.
        ports: the sub-topology's input ports, as `GncPartition.inputs` gives them.

    Returns:
        The pairs, in the converter's port order.

    Raises:
        ValueError: a role has no `<role>Out`, or a bus-typed one, naming the role; or a port is no
            role's, naming it.
    """
    converter = model.components[_CONVERTER]
    outputs = {port.name: port for port in converter.outputs}
    pairs = []
    for port in converter.inputs:
        bus = _carried(port)
        if not bus.startswith("Bus."):
            continue
        role = port.name.removesuffix("In")
        output = outputs.get(f"{role}Out")
        if output is None or _carried(output).startswith("Bus."):
            raise ValueError(
                f"{_CONVERTER}'s role {role} takes {bus} at {port.name} but has no {role}Out of a"
                " GNC type"
            )
        if port.name in ports:
            icd = _carried(output)
            pairs.append(Pair(role, fpp_types.named(bus), fpp_types.named(icd), port.name))
    unfed = sorted(set(ports) - {pair.port for pair in pairs})
    if unfed:
        raise ValueError(f"the sub-topology's inputs {unfed} are fed by no role of {_CONVERTER}")
    return pairs


@functools.cache
def _conversion(bus: type, icd: type) -> Any:
    """A bus struct's conversion to an ICD struct, planned once.

    Args:
        bus: the bus struct's tuple.
        icd: the ICD struct's tuple.

    Returns:
        The conversion.
    """
    return fpp_types.converter(bus, icd)


def convert(pairs: Sequence[Pair], messages: Mapping[str, Any]) -> dict[str, Any]:
    """Each pair's bus struct as its GNC port's value.

    Args:
        pairs: the pairs.
        messages: each role's bus struct, as RIO-in reads it.

    Returns:
        Each value, an ICD struct's tuple, by its GNC port.
    """
    return {pair.port: _conversion(pair.bus, pair.icd)(messages[pair.role]) for pair in pairs}
