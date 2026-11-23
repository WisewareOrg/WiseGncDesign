"""The Python build's RIO: each sensor's message read as its bus struct, each actuator's written.

The roles are the contract's `Cdh.BusConverter`'s, each with its bus struct's message from
`bus_messages`: RIO-in reads the sensor roles', and RIO-out builds the actuator roles' payloads.
"""

import re
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen import fpp_types
from fsw.codegen.deployment import contract_model
from fsw.codegen.fields import DTYPES
from fsw.codegen.roles import roles
from fsw.payloads import payload_type
from fsw.python.cdh import inputs, outputs
from fsw.python.rio.messages import check, reader, writer

DECLARED = roles(contract_model())
"""Every role of the contract's `Cdh.BusConverter`."""

ROLES = [role for role in DECLARED if role.sensor]
"""Every sensor role."""

PAIRS = inputs.pairings(ROLES)
"""A pair per sensor role: its message, through its bus struct, to the GNC's struct."""

ACTUATORS = [role for role in DECLARED if not role.sensor]
"""Every actuator role."""

COMMANDS = outputs.pairings(ACTUATORS)
"""A pair per actuator role: the GNC's struct, through its bus struct, to its message."""


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


def _assert_holds(holds: Callable[[Any, Mapping[str, Any]], None], bus: Any, message: Any, role: str) -> None:
    """A bus struct holds a bus message's values, each member an array of its FPP type.

    Args:
        holds: asserts a tuple holds values.
        bus: the bus struct's tuple, as read.
        message: the bus message: its struct, and each member's values by its FPP name.
        role: the role, named on failure.
    """
    holds(bus, message.values)
    for member in message.struct.members:
        got = getattr(bus, member.name)
        assert isinstance(got, np.ndarray), f"{role}.{member.name}"
        assert got.dtype == DTYPES[member.type], f"{role}.{member.name}"


def test_each_paired_role_s_message_is_read_as_its_bus_struct(
    bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """Each role's payload, as its reader gives it, is read as its bus struct.

    Args:
        bus_messages: a message of each bus struct.
        holds: asserts a tuple or payload holds values.
    """
    assert PAIRS
    for pair, role in zip(PAIRS, ROLES, strict=True):
        _, subscribed = _written(bus_messages[role.bus].payload)

        read_ = reader(pair)(subscribed())

        assert isinstance(read_, fpp_types.named(role.bus)), role.role
        _assert_holds(holds, read_, bus_messages[role.bus], role.role)


def test_a_payload_of_another_class_of_the_payload_s_name_reads_alike(
    bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """A payload whose class is not messaging's, and declares no fields, is read through its name.

    The Basilisk fact it rests on: once a simulation module that declares a message's payload is
    imported, SWIG returns a reader's payload as that module's class of the same name, which has no
    `__dtype__` but is a proxy of the same C struct, its `this`. This mock class is one such class,
    carrying the payload's fields and its `this`.

    Args:
        bus_messages: a message of each bus struct.
        holds: asserts a tuple or payload holds values.
    """
    for pair, role in zip(PAIRS, ROLES, strict=True):
        payload = bus_messages[role.bus].payload
        names = type(payload).__dtype__.names
        alias = type(type(payload).__name__, (), {n: getattr(payload, n) for n in [*names, "this"]})()
        assert not hasattr(alias, "__dtype__")

        read_ = reader(pair)(alias)

        _assert_holds(holds, read_, bus_messages[role.bus], role.role)


def test_a_read_message_keeps_its_values_after_the_next_tick(
    bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """The host's payload is a live view of its message; the conversion copies it.

    Each role's message is read, and written again with other values, as the next tick's sensor
    task does: the bus struct still holds the first tick's values.

    Args:
        bus_messages: a message of each bus struct.
        holds: asserts a tuple or payload holds values.
    """
    for pair, role in zip(PAIRS, ROLES, strict=True):
        message, subscribed = _written(bus_messages[role.bus].payload)
        payload = subscribed()
        read_ = reader(pair)(payload)
        later = type(bus_messages[role.bus].payload)()
        for field in type(later).__dtype__.names:
            setattr(later, field, [v + 100.0 for v in getattr(payload, field)])

        message.write(later)

        field = type(later).__dtype__.names[0]
        assert list(getattr(payload, field)) == list(getattr(later, field)), role.role
        _assert_holds(holds, read_, bus_messages[role.bus], role.role)


def test_a_read_message_s_arrays_are_read_only(bus_messages: dict[str, Any]):
    """Each array RIO-in reads cannot be changed in place, so CDH-in can pass it on uncopied.

    Args:
        bus_messages: a message of each bus struct.
    """
    for pair, role in zip(PAIRS, ROLES, strict=True):
        _, subscribed = _written(bus_messages[role.bus].payload)
        read_ = reader(pair)(subscribed())

        for value in (v for v in read_ if isinstance(v, np.ndarray)):
            with pytest.raises(ValueError, match="read-only"):
                value[...] = 0


def test_a_paired_role_without_its_message_is_refused_naming_it_and_another_role_is_not_read():
    """`check` refuses a vehicle lacking a paired role's message, and passes one with an extra role."""
    messages = {pair.role: payload_type(pair.bus.__qualname__)() for pair in PAIRS}

    check(PAIRS, {**messages, "other": object()})
    with pytest.raises(KeyError, match=re.escape(f"the role {PAIRS[0].role},")):
        check(PAIRS, {"other": object()})


def test_each_actuator_role_s_bus_struct_is_written_as_a_fresh_payload_of_its_message(
    bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """Each commanded role's bus struct becomes a new `messaging.<Name>Payload`, field by field.

    Each payload field is the bus member of its name, ignoring case; the bus struct changed
    afterwards leaves the payload as it was.

    Args:
        bus_messages: a message of each bus struct, its members' values distinct.
        holds: asserts a tuple or payload holds values.
    """
    assert COMMANDS
    buses = {
        pair.role: pair.bus(**{m: np.array(v) for m, v in bus_messages[role.bus].values.items()})
        for pair, role in zip(COMMANDS, ACTUATORS, strict=True)
    }

    written = {pair.role: writer(pair)(buses[pair.role]) for pair in COMMANDS}
    for bus in buses.values():
        for value in bus:
            value[...] = 0

    for role in ACTUATORS:
        payload = written[role.role]
        name = role.bus.removeprefix("Bus.")
        assert type(payload) is getattr(messaging, f"{name}Payload"), role.role
        holds(payload, bus_messages[role.bus].values)
