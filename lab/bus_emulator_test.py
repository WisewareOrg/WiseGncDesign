"""The bus emulator's bytes for each bus struct's message are F´'s serialization of the struct.

Each test ranges over every bus struct in `Bus.fpp`, through the `bus_messages` fixture, both ways:
a message to its bytes, and bytes back to a message. The pin tests are skipped without the
deployment `just fsw` builds, as the `fsw` fixture skips.
"""

import gc
import re
import struct
import weakref
from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

import pytest
from Basilisk.architecture.messaging.SCStatesMsgPayload import SCStatesMsgPayload

from fsw.codegen.fpp_model import Member, Struct
from lab import bus_emulator
from lab.bus_emulator import deserialize, from_bus, serialize, size, to_bus


def _assert_holds(holds: Callable[[Any, Mapping[str, Any]], None], payload: Any, message: Any, name: str) -> None:
    """A payload is a fresh `messaging.<Name>Payload` holding a bus message's values.

    Args:
        holds: asserts a payload holds values.
        payload: the payload.
        message: the `BusMessage`.
        name: the bus struct, named on failure.
    """
    assert type(payload) is type(message.payload), name
    assert payload is not message.payload, name
    holds(payload, message.values)


def test_a_message_with_no_bus_struct_is_refused_by_name() -> None:
    """A payload that no `Bus.<Name>` mirrors raises `KeyError` naming it."""
    with pytest.raises(KeyError, match="SCStatesMsgPayload"):
        serialize(SCStatesMsgPayload())


@pytest.mark.parametrize(
    ("member", "named"),
    [
        (Member("count", "F64", None), "count is F64"),
        (Member("flags", "bool", 3), r"flags is \[3\] bool"),
        (Member("ticks", "U32", 3), r"ticks is \[3\] U32"),
    ],
    ids=["scalar", "bool", "unused-primitive"],
)
def test_a_member_outside_the_emulator_s_domain_is_refused_by_name(
    member: Member, named: str, bus_messages: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mock bus struct with a scalar, `bool` or unused-primitive member raises, naming it.

    The mock, `Bus.Mock`, stands in for a bus struct's mirror for the test, and the copies are
    replanned.

    Args:
        member: the member outside the domain.
        named: the member as the refusal names it, a pattern.
        bus_messages: a message of each bus struct, one of whose payloads the mock mirrors.
        monkeypatch: replaces the struct's mirror for the test.
    """
    payload = next(iter(bus_messages.values())).payload
    mock = Struct("Bus.Mock", (member,))
    monkeypatch.setitem(bus_emulator._STRUCTS, type(payload), mock)
    bus_emulator._plan.cache_clear()
    try:
        with pytest.raises(KeyError, match=rf"Bus\.Mock\.{named}, which the bus emulator"):
            serialize(payload)
    finally:
        bus_emulator._plan.cache_clear()


def test_the_emulator_writes_the_bytes_f_prime_serializes(fsw: ModuleType, bus_messages: dict[str, Any]) -> None:
    """F´'s serialization of each bus struct from the same values equals the emulator's bytes.

    Each element of each message has its own value, so a misplaced member or byte order shows.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
    """
    for name, message in bus_messages.items():
        pin = getattr(fsw, re.sub(r"^Bus\.", "bus_", name))
        assert serialize(message.payload) == pin(**message.values), name


def test_the_emulator_reads_back_the_bytes_f_prime_serializes(
    fsw: ModuleType, bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
) -> None:
    """F´'s serialization of each bus struct, read back by the emulator, gives its values.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
        holds: asserts a payload holds values.
    """
    for name, message in bus_messages.items():
        pin = getattr(fsw, re.sub(r"^Bus\.", "bus_", name))
        _assert_holds(holds, deserialize(name, pin(**message.values)), message, name)


def test_a_bound_copy_reads_the_payload_and_the_buffer_as_they_stand_at_each_call(
    bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
) -> None:
    """A payload changed after binding is copied as changed, to the bus and back.

    Each struct's message is bound to a buffer of `size` bytes, then each value moved by one; the
    copy writes the moved values, `serialize`'s bytes of them, and reads them back into a payload.

    Args:
        bus_messages: a message of each bus struct.
        holds: asserts a payload holds values.
    """
    for name, message in bus_messages.items():
        buffer = bytearray(size(name))
        out = type(message.payload)()
        write, read = to_bus(message.payload, buffer), from_bus(buffer, out)
        fields = {field.lower(): field for field in type(message.payload).__dtype__.names}
        moved = {member: [value + 1.0 for value in values] for member, values in message.values.items()}
        for member, values in moved.items():
            setattr(message.payload, fields[member.lower()], values)

        write()
        read()

        assert bytes(buffer) == serialize(message.payload), name
        holds(out, moved)


def test_bytes_of_another_length_than_the_struct_s_are_refused_naming_both(bus_messages: dict[str, Any]) -> None:
    """Bytes one short of a struct's, and one over, raise `ValueError` naming the struct.

    Args:
        bus_messages: a message of each bus struct.
    """
    for name in bus_messages:
        for length in (size(name) - 1, size(name) + 1):
            with pytest.raises(ValueError, match=rf"{name} is {size(name)} bytes on the bus, not {length}"):
                deserialize(name, bytes(length))


def test_a_bound_copy_keeps_its_payload_alive(bus_messages: dict[str, Any]) -> None:
    """A payload the caller drops stays alive while a copy bound to it does.

    Args:
        bus_messages: a message of each bus struct.
    """
    for name, message in bus_messages.items():
        payload = type(message.payload)()
        alive = weakref.ref(payload)
        copy = to_bus(payload, bytearray(size(name)))
        del payload
        gc.collect()

        assert alive() is not None, name
        copy()


def test_members_out_of_the_payload_s_order_are_copied_as_separate_runs(
    bus_messages: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bus struct ordering members unlike the payload's C struct is planned as runs, and copied right.

    The mock, `Bus.Mock`, mirrors a bus struct's payload with its last member moved first, so the
    plan splits into runs, and the bytes are each member's values in the mock's order, big-endian.

    Args:
        bus_messages: a message of each bus struct.
        monkeypatch: replaces the payload's mirror for the test.
    """
    message = next(m for m in bus_messages.values() if len(m.struct.members) > 1)
    members = message.struct.members
    mock = Struct("Bus.Mock", (members[-1], *members[:-1]))
    expected = [value for member in mock.members for value in message.values[member.name]]
    monkeypatch.setitem(bus_emulator._STRUCTS, type(message.payload), mock)
    bus_emulator._plan.cache_clear()
    try:
        assert len(bus_emulator._plan(type(message.payload)).runs) == 2
        assert serialize(message.payload) == struct.pack(f">{len(expected)}d", *expected)
    finally:
        bus_emulator._plan.cache_clear()
