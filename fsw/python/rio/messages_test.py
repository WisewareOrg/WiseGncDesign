"""The Python build's RIO: each sensor's message read as its bus struct, each actuator's written.

The roles are the contract's `Cdh.BusConverter`'s, each with its bus struct's message from
`bus_messages`: RIO-in reads the sensor roles', and RIO-out builds the actuator roles' payloads.
"""

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from Basilisk.architecture import messaging
from Basilisk.architecture.messaging.NavAttMsgPayload import NavAttMsgPayload
from Basilisk.architecture.messaging.STSensorMsgPayload import STSensorMsgPayload

from fsw.codegen import fpp_types
from fsw.codegen.deployment import Contract, contract_model
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

MOCK = """\
module RioMock {

  struct StarTracker {
    timeTag: U64
    qInrtl2Case: [4] F64
  }

  struct Attitude {
    sigma_BN: [4] F64
  }

}
"""
"""Structs mirroring Basilisk payloads no bus struct does: `STSensorMsgPayload`, a scalar beside an
array, and a four-element attitude unlike `NavAttMsgPayload`'s three."""


@pytest.fixture(scope="module")
def mock(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """The mock's struct tuples, loaded once.

    Args:
        tmp_path_factory: where the mock's contract is written.

    Returns:
        Module `RioMock`'s tuples.
    """
    directory = tmp_path_factory.mktemp("rio")
    path = directory / "RioMock.fpp"
    path.write_text(MOCK)
    (directory / "gnc").mkdir()
    fpp_types.load(Contract((path,), Path(directory / "gnc")))
    return SimpleNamespace(**{name: fpp_types.named(f"RioMock.{name}") for name in ("StarTracker", "Attitude")})


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

        read_ = reader(pair.bus)(subscribed())

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

        read_ = reader(pair.bus)(alias)

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
        read_ = reader(pair.bus)(payload)
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
        read_ = reader(pair.bus)(subscribed())

        arrays = [v for v in read_ if isinstance(v, np.ndarray)]
        assert arrays, role.role
        for value in arrays:
            with pytest.raises(ValueError, match="read-only"):
                value[...] = 0


def test_each_basilisk_message_reads_as_its_bus_struct_member_for_member(
    bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """Each bus struct's payload reads as it, each member its values in its FPP type.

    Args:
        bus_messages: a message of each bus struct, its members' values distinct.
        holds: asserts a tuple holds values.
    """
    assert bus_messages
    for name, message in bus_messages.items():
        bus = reader(fpp_types.named(name))(message.payload)

        assert type(bus) is fpp_types.named(name), name
        holds(bus, message.values)
        for member in message.struct.members:
            value = getattr(bus, member.name)
            assert isinstance(value, np.ndarray), f"{name}.{member.name}"
            assert value.dtype == DTYPES[member.type], f"{name}.{member.name}"


def test_a_payload_reads_as_read_only_arrays_and_plain_scalars(mock: SimpleNamespace):
    """A payload is read from one copy of its memory: arrays read-only, a scalar a plain number.

    Args:
        mock: the mock's tuples.
    """
    payload = STSensorMsgPayload()
    payload.timeTag = 2**40 + 7
    payload.qInrtl2Case = [0.5, -0.5, 0.25, 1.0]

    read_ = reader(mock.StarTracker, STSensorMsgPayload)(payload)
    payload.qInrtl2Case = [0.0, 0.0, 0.0, 0.0]

    assert read_.timeTag == 2**40 + 7
    assert type(read_.timeTag) is int
    assert read_.qInrtl2Case.tolist() == [0.5, -0.5, 0.25, 1.0]
    with pytest.raises(ValueError, match="read-only"):
        read_.qInrtl2Case[0] = 1.0


def test_a_bus_struct_is_written_to_a_fresh_payload_field_by_field(mock: SimpleNamespace):
    """A bus struct is written into a fresh payload's memory, each field at its offset.

    The struct changed afterwards leaves the payload as it was, and a second write gives another
    payload.

    Args:
        mock: the mock's tuples.
    """
    source = mock.StarTracker(timeTag=2**40 + 7, qInrtl2Case=np.array([0.5, -0.5, 0.25, 1.0]))
    write = writer(mock.StarTracker, STSensorMsgPayload)

    payload = write(source)
    source.qInrtl2Case[...] = 0.0

    assert type(payload) is STSensorMsgPayload
    assert payload.timeTag == 2**40 + 7
    assert list(payload.qInrtl2Case) == [0.5, -0.5, 0.25, 1.0]
    assert write(source) is not payload


def test_a_bus_struct_whose_field_differs_from_the_payload_s_is_refused_when_planned(mock: SimpleNamespace):
    """Neither a reader nor a writer is planned when a field's shape differs, naming the field.

    Args:
        mock: the mock's tuples.
    """
    with pytest.raises(ValueError, match="sigma_BN"):
        reader(mock.Attitude, NavAttMsgPayload)
    with pytest.raises(ValueError, match="sigma_BN"):
        writer(mock.Attitude, NavAttMsgPayload)


def test_a_value_of_another_shape_than_its_field_is_refused_when_written(mock: SimpleNamespace):
    """A scalar written to an array field is refused, naming the field, rather than broadcast into it.

    Args:
        mock: the mock's tuples.
    """
    write = writer(mock.StarTracker, STSensorMsgPayload)

    with pytest.raises(ValueError, match=re.escape("StarTracker.qInrtl2Case is (4,), but its value is ()")):
        write(mock.StarTracker(timeTag=1, qInrtl2Case=0.5))


def test_a_paired_role_without_its_message_is_refused_naming_it_and_another_role_is_not_read():
    """`check` refuses a vehicle lacking a paired role's message, and passes one with an extra role."""
    messages = {pair.role: payload_type(pair.bus.__qualname__)() for pair in PAIRS}

    check(PAIRS, {**messages, "other": object()})
    with pytest.raises(KeyError, match=re.escape(f"the role {PAIRS[0].role},")):
        check(PAIRS, {"other": object()})


def test_a_paired_role_s_message_of_another_payload_class_is_refused_naming_both():
    """`check` refuses a payload whose class is not the one its role's bus struct mirrors."""
    pair = PAIRS[0]
    wanted = payload_type(pair.bus.__qualname__).__name__
    assert wanted != "SCStatesMsgPayload"

    with pytest.raises(TypeError, match=f"the role {pair.role}'s message is a SCStatesMsgPayload, .* mirrors {wanted}"):
        check([pair], {pair.role: payload_type("Bus.SCStatesMsg")()})


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

    written = {pair.role: writer(pair.bus)(buses[pair.role]) for pair in COMMANDS}
    for bus in buses.values():
        for value in bus:
            value[...] = 0

    for role in ACTUATORS:
        payload = written[role.role]
        name = role.bus.removeprefix("Bus.")
        assert type(payload) is getattr(messaging, f"{name}Payload"), role.role
        holds(payload, bus_messages[role.bus].values)
