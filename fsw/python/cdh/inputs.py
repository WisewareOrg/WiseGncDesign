"""The Python build's CDH-in: each sensor role's bus struct, converted to its GNC input's FPP type.

The pairing is FPP's, `Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp`, read by
`fsw.codegen.roles` as the F´ build's CDH reads it; a `Pair` names one role's. The bus struct is
converted to the ICD struct field by field with `fsw.codegen.fpp_types.converter`, every array a
fresh copy.
"""

import functools
from collections.abc import Collection, Mapping, Sequence
from typing import Any, NamedTuple

from fsw.codegen import fpp_types
from fsw.codegen.fpp_model import Model
from fsw.codegen.roles import CONVERTER, roles

__all__ = ["Pair", "convert", "pairings"]


class Pair(NamedTuple):
    """A role's message, from its bus struct to the ICD struct its GNC port takes.

    Attributes:
        role: the vehicle's role, `<role>`.
        bus: the bus struct's tuple, mirroring the role's Basilisk message.
        icd: the ICD struct's tuple, which the GNC port takes.
        port: the GNC sub-topology's port, `<role>In`.
    """

    role: str
    bus: type
    icd: type
    port: str


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
    pairs = [
        Pair(role.role, fpp_types.named(role.bus), fpp_types.named(role.icd), role.input)
        for role in roles(model)
        if role.input in ports
    ]
    unfed = sorted(set(ports) - {pair.port for pair in pairs})
    if unfed:
        raise ValueError(f"the sub-topology's inputs {unfed} are fed by no role of {CONVERTER}")
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
