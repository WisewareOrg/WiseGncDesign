"""The Python build's RIO: each sensor role's Basilisk message read as its bus struct, and back.

Each role's reading is planned once, from the payload class its bus struct mirrors by
`fsw.payloads.payload_type`, through `fsw.codegen.fpp_types.converter`. RIO-in reads a payload into
a fresh, read-only copy: the host's payload is a live view of its message, which the next dynamics
step overwrites, and CDH-in passes the copy's arrays to GNC uncopied. SWIG can return the payload as
another module's class of the same name, such as a simulation module's once that module is imported;
that class is a proxy of the same C struct, so it reads alike. RIO-out writes each actuator role's
bus struct into a fresh payload of that class, each field from the bus member of its name, ignoring
case.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from fsw.codegen.fpp_types import converter
from fsw.payloads import payload_type
from fsw.python.cdh.inputs import Pair

__all__ = ["check", "reader", "writer"]


def check(pairs: Sequence[Pair], messages_by_role: Mapping[str, Any]) -> None:
    """Checks each paired role has a message, of the payload class its bus struct mirrors.

    A role no pair names is not read, so not checked.

    Args:
        pairs: the sensor roles' pairs.
        messages_by_role: each role's Basilisk message payload, as the host gives it.

    Raises:
        KeyError: a paired role has no message, naming it.
        TypeError: a role's payload is of another class than its bus struct mirrors, by name,
            naming both.
    """
    for pair in pairs:
        if pair.role not in messages_by_role:
            raise KeyError(
                f"the configuration takes the role {pair.role}, which the vehicle's messages"
                f" {sorted(messages_by_role)} lack"
            )
        given = type(messages_by_role[pair.role]).__name__
        wanted = payload_type(pair.bus.__qualname__).__name__
        if given != wanted:
            raise TypeError(f"the role {pair.role}'s message is a {given}, but its bus struct mirrors {wanted}")


def reader(pair: Pair) -> Callable[[Any], Any]:
    """RIO-in for one sensor role: its message's payload, read as its bus struct.

    Args:
        pair: the role's pair.

    Returns:
        A function of the role's payload, as the host gives it, returning its bus struct's tuple,
        its arrays fresh and read-only.
    """
    return converter(payload_type(pair.bus.__qualname__), pair.bus)


def writer(pair: Pair) -> Callable[[Any], Any]:
    """RIO-out for one actuator role: its bus struct, written as a fresh payload of its message.

    Args:
        pair: the role's pair.

    Returns:
        A function of the role's bus struct's tuple, as CDH-out gives it, returning a fresh
        `messaging.<Name>Payload` of the message it mirrors.
    """
    return converter(pair.bus, payload_type(pair.bus.__qualname__))
