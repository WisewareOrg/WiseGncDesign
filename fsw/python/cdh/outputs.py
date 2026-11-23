"""The Python build's CDH-out: each actuator role's GNC output, converted to its bus struct.

The pairing is FPP's, `Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp`, read by
`fsw.codegen.roles` as the F´ build's CDH reads it, each actuator role's a `Pair` as CDH-in's. The
ICD struct is converted to the bus struct field by field with `fsw.codegen.fpp_types.converter`,
each bus field the ICD field of its name, ignoring case, uncopied: RIO-out copies it into the
payload in the same tick.
"""

from collections.abc import Callable, Sequence
from typing import Any

from fsw.codegen import fpp_types
from fsw.codegen.roles import Role
from fsw.python.cdh.inputs import Pair

__all__ = ["converter", "pairings"]


def pairings(roles: Sequence[Role]) -> list[Pair]:
    """Each actuator role's pair, from the ICD struct its port `<role>Out` sends to its bus struct.

    Args:
        roles: the actuator roles a configuration takes, as `fsw.codegen.roles.taken` gives them.

    Returns:
        The pairs, in the roles' order.
    """
    return [Pair(role.role, fpp_types.named(role.bus), fpp_types.named(role.icd), role.output) for role in roles]


def converter(pair: Pair) -> Callable[[Any], Any]:
    """CDH-out for one actuator role: its GNC output's ICD struct, as its bus struct.

    Args:
        pair: the role's pair.

    Returns:
        A function of the ICD struct's tuple GNC wrote, returning the role's bus struct's tuple,
        which holds the ICD struct's arrays: RIO-out copies them into the payload.
    """
    return fpp_types.converter(pair.icd, pair.bus, copy=False)
