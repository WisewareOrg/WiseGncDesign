"""The bus emulator's bytes for each bus struct's message are F´'s serialization of the struct.

Each test ranges over every bus struct in `Bus.fpp`, through the `bus_messages` fixture. The pin
test is skipped without the deployment `just fsw` builds, as the `fsw` fixture skips.
"""

import re
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fields import DTYPES
from fsw.codegen.fpp_model import Member, Struct
from lab import bus_emulator
from lab.bus_emulator import serialize


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

    Args:
        bus_messages: a message of each bus struct.
    """
    assert bus_messages
    for name, message in bus_messages.items():
        assert serialize(message.payload) == _packed(message), name


def test_the_same_members_little_endian_are_other_bytes(bus_messages: dict[str, Any]) -> None:
    """The comparison above tells byte orders apart: each struct's members little-endian differ.

    Args:
        bus_messages: a message of each bus struct.
    """
    for name, message in bus_messages.items():
        assert serialize(message.payload) != _packed(message, "<"), name


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
    """A toy bus struct with a scalar, `bool` or unused-primitive member raises, naming it.

    The toy, `Bus.Toy`, stands in for a bus struct's mirror for the test, and the packers are
    replanned.

    Args:
        member: the member outside the domain.
        named: the member as the refusal names it, a pattern.
        bus_messages: a message of each bus struct, one of whose payloads the toy mirrors.
        monkeypatch: replaces the struct's mirror for the test.
    """
    payload = next(iter(bus_messages.values())).payload
    toy = Struct("Bus.Toy", (member,))
    monkeypatch.setitem(bus_emulator._STRUCTS, type(payload).__name__.lower(), toy)
    bus_emulator._packer.cache_clear()
    try:
        with pytest.raises(KeyError, match=rf"Bus\.Toy\.{named}, which the bus emulator"):
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
