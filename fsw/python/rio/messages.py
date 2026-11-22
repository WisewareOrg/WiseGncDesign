"""The Python build's RIO: each sensor role's Basilisk message read as its bus struct, and back.

A message is read field by field with `fsw.codegen.fpp_types.converter`, so every array is a fresh
copy: the host's payload is a view of its reader's buffer, valid only during its tick. Its fields
are read through `Basilisk.architecture.messaging`'s class of its name, which declares them: SWIG
can return the payload as another module's class of that name, such as a simulation module's
once that module is imported, which does not. Each actuator role's bus struct is written as a
fresh payload of the class `fsw.payloads.payload_type` gives, each field from the bus member of
its name, ignoring case.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from Basilisk.architecture import messaging

from fsw.codegen.fpp_types import converter
from fsw.payloads import payload_type
from fsw.python.cdh.inputs import Pair

__all__ = ["commands", "read"]


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
        read_[pair.role] = converter(getattr(messaging, type(message).__name__), pair.bus)(message)
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


def _payload(bus: Any) -> Any:
    """A bus struct as a fresh payload of the Basilisk message it mirrors.

    Args:
        bus: the bus struct's tuple, `Bus.<Name>`.

    Returns:
        The `messaging.<Name>Payload` it mirrors, by `fsw.payloads.payload_type`, each field the
        bus member of its name, ignoring case.
    """
    payload = payload_type(type(bus).__qualname__)()
    fields = {name.lower(): name for name in type(payload).__dtype__.names}
    for member, value in zip(bus._fields, bus, strict=True):
        setattr(payload, fields[member.lower()], np.asarray(value).tolist())
    return payload
