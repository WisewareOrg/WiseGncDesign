"""The Python build's CDH-in: each role's Basilisk message, converted to its GNC input's FPP type.

A `Pair` names a vehicle role, the bus struct its message mirrors, the ICD struct the GNC takes and
the GNC sub-topology's port it enters by. The message is converted to the bus struct and the bus
struct to the ICD struct, each field by name with `fsw.codegen.fpp_types.converter`, so every array
is a fresh copy: the host's payload is a view of its reader's buffer, valid only during its tick.
A payload's fields are read through `Basilisk.architecture.messaging`'s class of its name, which
declares them: SWIG can return the payload as another module's class of that name, such as
`Basilisk.simulation.imuSensor`'s once that module is imported, which does not.
"""

import functools
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

from Basilisk.architecture import messaging

from fsw.codegen.fpp_types import converter

__all__ = ["Pair", "convert"]


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


@functools.cache
def _conversion(payload: type, bus: type, icd: type) -> Callable[[Any], Any]:
    """A payload type's conversion through a bus struct to an ICD struct, planned once.

    Args:
        payload: the Basilisk message payload's type.
        bus: the bus struct's tuple.
        icd: the ICD struct's tuple.

    Returns:
        The conversion.
    """
    to_bus = converter(getattr(messaging, payload.__name__), bus)
    to_icd = converter(bus, icd)
    return lambda message: to_icd(to_bus(message))


def convert(pairs: Sequence[Pair], messages_by_role: Mapping[str, Any]) -> dict[str, Any]:
    """Each pair's message as its GNC port's value.

    Args:
        pairs: the pairs.
        messages_by_role: each role's Basilisk message payload, as the host gives it; a role no
            pair names is not read.

    Returns:
        Each value, an ICD struct's tuple, by its GNC port.
    """
    converted = {}
    for pair in pairs:
        message = messages_by_role[pair.role]
        converted[pair.port] = _conversion(type(message), pair.bus, pair.icd)(message)
    return converted
