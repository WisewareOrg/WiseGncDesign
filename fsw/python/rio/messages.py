"""The Python build's RIO: each sensor role's Basilisk message read as its bus struct, and back.

A message is read field by field with `fsw.codegen.fpp_types.converter`, so every array is a fresh
copy: the host's payload is a view of its reader's buffer, valid only during its tick. Its fields
are read through `Basilisk.architecture.messaging`'s class of its name, which declares them: SWIG
can return the payload as another module's class of that name, such as a simulation module's
once that module is imported, which does not. Each actuator role's bus struct `Bus.<Name>` is
written as a fresh `messaging.<Name>Payload`, each field from the bus member of its name, ignoring
case, as `fsw/fpp/interfaces/bus_test.py` holds them.
"""

import functools
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
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


def commands(pairs: Sequence[Pair], buses: Mapping[str, Any]) -> dict[str, Any]:
    """Each commanded actuator role's bus struct, as a fresh payload of the message it mirrors.

    Args:
        pairs: the actuator roles' pairs.
        buses: each commanded role's bus struct's tuple, as CDH-out gives them; a role absent is
            not commanded this tick.

    Returns:
        Each role's `messaging.<Name>Payload`, by the role, for the roles commanded.
    """
    return {pair.role: _payload(buses[pair.role]) for pair in pairs if pair.role in buses}


@functools.cache
def _payloads() -> dict[str, type]:
    """Each of `messaging`'s payload classes, by its name in lower case, read once.

    Returns:
        The classes.
    """
    return {n.lower(): getattr(messaging, n) for n in dir(messaging) if n.endswith("Payload")}


def _payload(bus: Any) -> Any:
    """A bus struct as a fresh payload of the Basilisk message it mirrors.

    Args:
        bus: the bus struct's tuple, `Bus.<Name>`.

    Returns:
        The `messaging.<Name>Payload` it mirrors, matched ignoring case, each field the bus member
        of its name, ignoring case.
    """
    payload = _payloads()[type(bus).__name__.lower() + "payload"]()
    fields = {name.lower(): name for name in type(payload).__dtype__.names}
    for member, value in zip(bus._fields, bus, strict=True):
        setattr(payload, fields[member.lower()], np.asarray(value).tolist())
    return payload
