"""The Python build's RIO: each sensor role's Basilisk message read as its bus struct, and back.

Each role's reading is planned once, from the payload class its bus struct mirrors by
`fsw.payloads.payload_type`, through `fsw.codegen.fpp_types.converter`. RIO-in reads a payload
into a fresh, read-only copy: the host's payload is a live view of its message, which the next
dynamics step overwrites, and CDH-in passes the copy's arrays to GNC uncopied. SWIG can return the
payload as another module's class of the same name, such as a simulation module's once that module
is imported, a proxy of the same C struct, which reads alike. RIO-out writes each actuator role's
bus struct into a fresh payload of that class, each field from the bus member of its name, ignoring
case.
"""

from collections.abc import Callable
from typing import Any

from fsw.codegen.fpp_types import converter
from fsw.payloads import payload_type
from fsw.python.cdh.inputs import Pair

__all__ = ["reader", "writer"]


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
