"""The Python build's RIO-in reads each paired role's Basilisk message as its bus struct.

The roles are the contract's `Cdh.BusConverter`'s, each with its bus struct's message from
`bus_messages`.
"""

import re
from typing import Any

import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen import fpp_types
from fsw.codegen.deployment import contract_files
from fsw.codegen.fields import DTYPES
from fsw.codegen.fpp_model import read as read_model
from fsw.codegen.roles import roles
from fsw.python.cdh.inputs import Pair
from fsw.python.rio.messages import read

ROLES = roles(read_model(contract_files()))
"""Every role of the contract's `Cdh.BusConverter`."""

PAIRS = [
    Pair(role.role, fpp_types.named(role.bus), fpp_types.named(role.icd), role.input)
    for role in ROLES
]
"""A pair per role: its message, through its bus struct, to the GNC's struct."""


def _written(payload: Any) -> tuple[Any, Any]:
    """A message of a payload's type, written with it, and a reader subscribed to it.

    Args:
        payload: the payload, of `messaging.<Name>Payload`.

    Returns:
        The message, `messaging.<Name>`, and its reader, `messaging.<Name>Reader`.
    """
    name = type(payload).__name__.removesuffix("Payload")
    message = getattr(messaging, name)()
    message.write(payload)
    reader = getattr(messaging, f"{name}Reader")()
    reader.subscribeTo(message)
    return message, reader


def _assert_holds(bus: Any, message: Any, role: str) -> None:
    """A bus struct holds a bus message's values, each member an array of its FPP type.

    Args:
        bus: the bus struct's tuple, as read.
        message: the bus message: its struct, and each member's values by its FPP name.
        role: the role, named on failure.
    """
    for member in message.struct.members:
        got = getattr(bus, member.name)
        assert isinstance(got, np.ndarray), f"{role}.{member.name}"
        np.testing.assert_array_equal(got, message.values[member.name], err_msg=role)
        assert got.dtype == DTYPES[member.type], f"{role}.{member.name}"


def test_each_paired_role_s_message_is_read_as_its_bus_struct(bus_messages: dict[str, Any]):
    """Each role's payload is read as its bus struct; a role no pair names is not read.

    Args:
        bus_messages: a message of each bus struct.
    """
    assert PAIRS
    readers = {}
    for role in ROLES:
        _, readers[role.role] = _written(bus_messages[role.bus].payload)

    read_ = read(PAIRS, {**{r: reader() for r, reader in readers.items()}, "other": object()})

    assert list(read_) == [role.role for role in ROLES]
    for role in ROLES:
        assert isinstance(read_[role.role], fpp_types.named(role.bus)), role.role
        _assert_holds(read_[role.role], bus_messages[role.bus], role.role)


def test_a_payload_of_another_class_of_the_payload_s_name_reads_alike(
    bus_messages: dict[str, Any],
):
    """A payload whose class is not messaging's, and declares no fields, is read through its name.

    The Basilisk fact it rests on: once a simulation module that declares a message's payload is
    imported, SWIG returns a reader's payload as that module's class of the same name, which has no
    `__dtype__`. This mock class is one such class, carrying the payload's fields.

    Args:
        bus_messages: a message of each bus struct.
    """
    for pair, role in zip(PAIRS, ROLES, strict=True):
        payload = bus_messages[role.bus].payload
        names = type(payload).__dtype__.names
        alias = type(type(payload).__name__, (), {n: getattr(payload, n) for n in names})()
        assert not hasattr(alias, "__dtype__")

        read_ = read([pair], {role.role: alias})[role.role]

        _assert_holds(read_, bus_messages[role.bus], role.role)


def test_a_read_message_keeps_its_values_after_the_next_tick(bus_messages: dict[str, Any]):
    """The host's payload is a live view of the reader's buffer; the conversion copies it.

    Each role's message is read, and written again with other values, as the next tick's sensor
    task does: the bus struct still holds the first tick's values.

    Args:
        bus_messages: a message of each bus struct.
    """
    for pair, role in zip(PAIRS, ROLES, strict=True):
        message, reader = _written(bus_messages[role.bus].payload)
        payload = reader()
        read_ = read([pair], {role.role: payload})[role.role]
        later = type(bus_messages[role.bus].payload)()
        for field in type(later).__dtype__.names:
            setattr(later, field, [v + 100.0 for v in getattr(payload, field)])

        message.write(later)

        field = type(later).__dtype__.names[0]
        assert list(getattr(payload, field)) == list(getattr(later, field)), role.role
        _assert_holds(read_, bus_messages[role.bus], role.role)


def test_a_paired_role_the_vehicle_does_not_have_is_refused_naming_it():
    """A vehicle without a paired role's message fails the tick, naming the role."""
    with pytest.raises(KeyError, match=re.escape(f"the role {PAIRS[0].role}")):
        read(PAIRS, {"notARole": object()})
