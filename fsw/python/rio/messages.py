"""The Python build's RIO: each paired role's Basilisk message read as its bus struct, and back.

A message is read field by field with `fsw.codegen.fpp_types.converter`, so every array is a fresh
copy: the host's payload is a view of its reader's buffer, valid only during its tick. Its fields
are read through `Basilisk.architecture.messaging`'s class of its name, which declares them: SWIG
can return the payload as another module's class of that name, such as
`Basilisk.simulation.imuSensor`'s once that module is imported, which does not.
"""

import functools
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from Basilisk.architecture import messaging

from fsw.codegen.fpp_types import converter
from fsw.python.cdh.inputs import Pair

__all__ = ["commands", "read"]


@functools.cache
def _conversion(payload: type, bus: type) -> Callable[[Any], Any]:
    """A payload type's conversion to a bus struct, planned once.

    Args:
        payload: the Basilisk message payload's type.
        bus: the bus struct's tuple.

    Returns:
        The conversion.
    """
    return converter(getattr(messaging, payload.__name__), bus)


def read(pairs: Sequence[Pair], messages_by_role: Mapping[str, Any]) -> dict[str, Any]:
    """Each paired role's message, as its bus struct.

    Args:
        pairs: the pairs.
        messages_by_role: each role's Basilisk message payload, as the host gives it; a role no
            pair names is not read.

    Returns:
        Each bus struct's tuple, by its role.

    Raises:
        KeyError: a paired role has no message, naming it.
    """
    read_ = {}
    for pair in pairs:
        if pair.role not in messages_by_role:
            raise KeyError(
                f"the configuration takes the role {pair.role}, which the vehicle's messages"
                f" {sorted(messages_by_role)} lack"
            )
        message = messages_by_role[pair.role]
        read_[pair.role] = _conversion(type(message), pair.bus)(message)
    return read_


def commands() -> dict[str, Any]:
    """The actuator commands of a tick: none, since no actuator is written.

    Returns:
        No command, by role.
    """
    return {}
