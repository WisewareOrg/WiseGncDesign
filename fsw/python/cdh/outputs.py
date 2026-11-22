"""The Python build's CDH-out: each actuator role's GNC output, converted to its bus struct.

The pairing is FPP's, `Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp`, read by
`fsw.codegen.roles` as the F´ build's CDH reads it, each actuator role's a `Pair` as CDH-in's. The
ICD struct is converted to the bus struct field by field with `fsw.codegen.fpp_types.converter`,
every array a fresh copy: each bus field from the ICD field of its name, ignoring case.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from fsw.codegen import fpp_types
from fsw.codegen.roles import Role
from fsw.python.cdh.inputs import Pair

__all__ = ["convert", "pairings"]


def pairings(roles: Sequence[Role]) -> list[Pair]:
    """Each actuator role's pair, from the ICD struct its port `<role>Out` sends to its bus struct.

    Args:
        roles: the actuator roles a configuration takes, as `fsw.codegen.roles.taken` gives them.

    Returns:
        The pairs, in the roles' order.
    """
    return [Pair(role.role, fpp_types.named(role.bus), fpp_types.named(role.icd), role.output) for role in roles]


def convert(pairs: Sequence[Pair], values: Mapping[str, Any]) -> dict[str, Any]:
    """Each written GNC output as its role's bus struct.

    Args:
        pairs: the pairs.
        values: each GNC output port's value written in the frame, by the port, as the frame
            gives them; a port not written is absent.

    Returns:
        Each bus struct's tuple, by its role, for the ports written.
    """
    return {
        pair.role: fpp_types.converter(pair.icd, pair.bus)(values[pair.port]) for pair in pairs if pair.port in values
    }
