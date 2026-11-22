"""The bus emulator's bytes for each bus struct's message are F´'s serialization of the struct.

Each test ranges over every bus struct in `Bus.fpp`, through the `bus_messages` fixture, both ways:
a message to its bytes, and bytes back to a message. The pin tests are skipped without the
deployment `just fsw` builds, as the `fsw` fixture skips.
"""

import re
import struct
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fields import DTYPES
from fsw.codegen.fpp_model import Member, Struct
from lab import bus_emulator
from lab.bus_emulator import deserialize, serialize


def _packed(message: Any, order: str = ">", swap: tuple[str, str] | None = None) -> bytes:
    """A bus message's members packed in declaration order, by numpy rather than the emulator.

    Args:
        message: the `BusMessage`.
        order: the byte order, `>` or `<`.
        swap: two members whose values trade places, or none.

    Returns:
        The bytes.
    """
    values = dict(message.values)
    if swap:
        first, second = swap
        values[first], values[second] = values[second], values[first]
    return b"".join(
        np.asarray(values[m.name], DTYPES[m.type].newbyteorder(order)).tobytes()
        for m in message.struct.members
    )


def _swappable(struct: Struct) -> tuple[str, str] | None:
    """Two members of one type and size, which a swap leaves the same length.

    Args:
        struct: the bus struct.

    Returns:
        The two members' names, or none when the struct has no such pair.
    """
    for i, first in enumerate(struct.members):
        for second in struct.members[i + 1 :]:
            if (first.type, first.size) == (second.type, second.size):
                return first.name, second.name
    return None


def test_each_message_is_its_members_big_endian_and_packed_in_declaration_order(
    bus_messages: dict[str, Any],
) -> None:
    """Each struct's bytes are its members' values, big-endian, in `Bus.fpp`'s order.

    The comparison tells byte orders apart: each struct's members little-endian differ.

    Args:
        bus_messages: a message of each bus struct.
    """
    assert bus_messages
    for name, message in bus_messages.items():
        assert serialize(message.payload) == _packed(message), name
        assert serialize(message.payload) != _packed(message, "<"), name


def _assert_holds(payload: Any, message: Any, name: str) -> None:
    """A payload is a fresh `messaging.<Name>Payload` holding a bus message's values.

    Args:
        payload: the payload.
        message: the `BusMessage`.
        name: the bus struct, named on failure.
    """
    assert type(payload) is type(message.payload), name
    assert payload is not message.payload, name
    fields = {field.lower(): field for field in type(payload).__dtype__.names}
    for member in message.struct.members:
        got = getattr(payload, fields[member.name.lower()])
        np.testing.assert_array_equal(got, message.values[member.name], err_msg=name)


def test_each_struct_s_bytes_are_read_back_as_a_payload_of_the_message_it_mirrors(
    bus_messages: dict[str, Any],
) -> None:
    """Each struct's big-endian packed bytes give back its values; its little-endian bytes do not.

    Args:
        bus_messages: a message of each bus struct.
    """
    for name, message in bus_messages.items():
        _assert_holds(deserialize(name, _packed(message)), message, name)
        with pytest.raises(AssertionError):
            _assert_holds(deserialize(name, _packed(message, "<")), message, name)


def test_bytes_of_another_length_than_the_struct_s_are_refused(
    bus_messages: dict[str, Any],
) -> None:
    """Bytes one short of a struct's raise `struct.error`.

    Args:
        bus_messages: a message of each bus struct.
    """
    for name, message in bus_messages.items():
        with pytest.raises(struct.error):
            deserialize(name, _packed(message)[:-1])


def test_a_message_with_no_bus_struct_is_refused_by_name() -> None:
    """A payload that no `Bus.<Name>` mirrors raises `KeyError` naming it."""
    with pytest.raises(KeyError, match="SCStatesMsgPayload"):
        serialize(messaging.SCStatesMsgPayload())


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

    The mock, `Bus.Mock`, stands in for a bus struct's mirror for the test, and the packers are
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
    bus_emulator._packer.cache_clear()
    try:
        with pytest.raises(KeyError, match=rf"Bus\.Mock\.{named}, which the bus emulator"):
            serialize(payload)
    finally:
        bus_emulator._packer.cache_clear()


def test_the_emulator_writes_the_bytes_f_prime_serializes(
    fsw: ModuleType, bus_messages: dict[str, Any]
) -> None:
    """F´'s serialization of each bus struct from the same values equals the emulator's bytes.

    A little-endian emulator's bytes differ from F´'s, and so do a swapped-member emulator's for
    each struct with two members of one type and size, at least one struct among them, so the
    check can fail.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
    """
    swapped = 0
    for name, message in bus_messages.items():
        pin = getattr(fsw, re.sub(r"^Bus\.", "bus_", name))
        serialized = pin(**message.values)
        assert serialize(message.payload) == serialized, name
        assert _packed(message, "<") != serialized, name
        if pair := _swappable(message.struct):
            assert _packed(message, swap=pair) != serialized, name
            swapped += 1
    assert swapped


def test_the_emulator_reads_back_the_bytes_f_prime_serializes(
    fsw: ModuleType, bus_messages: dict[str, Any]
) -> None:
    """F´'s serialization of each bus struct, read back by the emulator, gives its values.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
    """
    for name, message in bus_messages.items():
        pin = getattr(fsw, re.sub(r"^Bus\.", "bus_", name))
        _assert_holds(deserialize(name, pin(**message.values)), message, name)
