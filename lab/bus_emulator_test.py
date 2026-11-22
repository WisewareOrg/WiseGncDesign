"""The bus emulator's bytes for each bus struct's message are F´'s serialization of the struct.

Each test ranges over every bus struct in `Bus.fpp`, through the `bus_messages` fixture, both ways:
a message to its bytes, and bytes back to a message. The pin tests are skipped without the
deployment `just fsw` builds, as the `fsw` fixture skips.
"""

import re
from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fpp_model import Member, Struct
from lab import bus_emulator
from lab.bus_emulator import deserialize, serialize


def _assert_holds(
    holds: Callable[[Any, Mapping[str, Any]], None], payload: Any, message: Any, name: str
) -> None:
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
