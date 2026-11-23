"""The Python build's CDH-in: each sensor role's bus struct, converted to its GNC input's FPP type.

The pairing is FPP's, `Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp`, read by
`fsw.codegen.roles` as the F´ build's CDH reads it; a `Pair` names one role's. The bus struct is
converted to the ICD struct field by field with `fsw.codegen.fpp_types.converter`, each array
RIO-in's own, uncopied (ADR 0005 rev 3). CDH-out, `fsw.python.cdh.outputs`, pairs the actuator
roles with the same `Pair`.
"""

from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

from fsw.codegen import fpp_types
from fsw.codegen.roles import Role

__all__ = ["Pair", "converter", "pairings"]


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


def converter(pair: Pair) -> Callable[[Any], Any]:
    """CDH-in for one sensor role: its bus struct, as its GNC port's ICD struct.

    Args:
        pair: the role's pair.

    Returns:
        A function of the role's bus struct's tuple, as RIO-in reads it, returning its ICD struct's
        tuple, which holds the bus struct's arrays.
    """
    return fpp_types.converter(pair.bus, pair.icd, copy=False)
