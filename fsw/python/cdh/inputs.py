"""The Python build's CDH-in: each sensor role's bus struct, converted to its GNC input's FPP type.

The pairing is FPP's, `Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp`, read by
`fsw.codegen.roles` as the F´ build's CDH reads it; a `Pair` names one role's. The bus struct is
converted to the ICD struct field by field with `fsw.codegen.fpp_types.converter`, every array a
fresh copy. CDH-out, `fsw.python.cdh.outputs`, pairs the actuator roles with the same `Pair`.
"""

from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from fsw.codegen import fpp_types
from fsw.codegen.roles import Role

__all__ = ["Pair", "convert", "pairings"]


class Pair(NamedTuple):
    """A role's struct, between the bus and the GNC sub-topology's port.

    Attributes:
        role: the vehicle's role, `<role>`.
        bus: the bus struct's tuple, mirroring the role's Basilisk message.
        icd: the ICD struct's tuple, which the GNC port takes or sends.
        port: the GNC sub-topology's port: `<role>In` for a sensor, `<role>Out` for an actuator.
    """

    role: str
    bus: type
    icd: type
    port: str


def pairings(roles: Sequence[Role]) -> list[Pair]:
    """Each sensor role's pair, from its bus struct to the ICD struct its port `<role>In` takes.

    Args:
        roles: the sensor roles a configuration takes, as `fsw.codegen.roles.taken` gives them.

    Returns:
        The pairs, in the roles' order.
    """
    return [Pair(role.role, fpp_types.named(role.bus), fpp_types.named(role.icd), role.input) for role in roles]


def convert(pairs: Sequence[Pair], messages: Mapping[str, Any]) -> dict[str, Any]:
    """Each pair's bus struct as its GNC port's value.

    Args:
        pairs: the pairs.
        messages: each role's bus struct, as RIO-in reads it.

    Returns:
        Each value, an ICD struct's tuple, by its GNC port.
    """
    return {pair.port: fpp_types.converter(pair.bus, pair.icd)(messages[pair.role]) for pair in pairs}
