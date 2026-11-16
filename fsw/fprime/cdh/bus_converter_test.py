"""The generated `Cdh.BusConverter` converts each role's bus struct to its GNC struct in F´.

Through each role's test pin `cdh_<role>`: the bus emulator's bytes for the role's message,
deserialized by F´, converted by the generated conversion and serialized back, compared with the
GNC struct `fsw.codegen.fields.plan` takes from the same values. Each test ranges over every role
of the contract's `Cdh.BusConverter`. Skipped without the deployment `just fsw` builds, as the
`fsw` fixture skips.
"""

import functools
import re
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from fsw.codegen.deployment import contract_files
from fsw.codegen.fields import DTYPES, form, plan
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.roles import Role, roles
from lab.bus_emulator import serialize


@functools.cache
def _contract() -> Model:
    """The contract's model, read once.

    Returns:
        The model.
    """
    return read(contract_files())


def _bytes(values: list[tuple[Any, list[Any]]]) -> bytes:
    """Values serialized as F´ does, big-endian and packed, by numpy rather than F´.

    Args:
        values: each field's element type, a numpy type, and its values, in order.

    Returns:
        The bytes.
    """
    return b"".join(np.asarray(v, dtype.newbyteorder(">")).tobytes() for dtype, v in values)


def _planned(role: Role) -> list[Any]:
    """The field rule's plan of a role's GNC struct from its bus struct.

    Args:
        role: the role.

    Returns:
        Each GNC member, its bus field's name and its form.
    """
    model = _contract()
    bus = model.types[role.bus]
    sources = {m.name.lower(): (m.name, form(m, model.types)) for m in bus.members}
    return plan(model.types[role.icd], model.types, sources, role.bus)


def _reading(role: Role, bus_values: dict[str, list[Any]]) -> bytes:
    """The GNC struct the field rule takes from a bus struct's values, serialized.

    Args:
        role: the role.
        bus_values: each bus member's values by its FPP name.

    Returns:
        The GNC struct's bytes.
    """
    return _bytes([(element, bus_values[name]) for _, name, (_, element) in _planned(role)])


def _bus_bytes(message: Any, swap: tuple[str, str] | None = None) -> bytes:
    """A bus message's bytes laid out by its struct, with two members' places traded or not.

    Args:
        message: the `BusMessage`.
        swap: two members whose values trade places, or none.

    Returns:
        The bytes.
    """
    values = dict(message.values)
    if swap:
        first, second = swap
        values[first], values[second] = values[second], values[first]
    return _bytes([(DTYPES[m.type], values[m.name]) for m in message.struct.members])


def _roles() -> list[Role]:
    """Every role of the contract's `Cdh.BusConverter`, at least one.

    Returns:
        The roles.
    """
    found = roles(_contract())
    assert found
    return found


def test_each_role_s_bus_struct_converts_to_its_gnc_struct(
    fsw: ModuleType, bus_messages: dict[str, Any]
) -> None:
    """Each role's pin gives the GNC struct the field rule takes from the emulator's bytes.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
    """
    for role in _roles():
        message = bus_messages[role.bus]
        converted = getattr(fsw, f"cdh_{role.role}")(serialize(message.payload))
        assert converted == _reading(role, message.values), role.role


def test_each_pin_reads_the_bytes_by_the_bus_layout(
    fsw: ModuleType, bus_messages: dict[str, Any]
) -> None:
    """Bytes with a converted member and another of its form traded give the traded reading.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
    """
    swapped = 0
    for role in _roles():
        message = bus_messages[role.bus]
        converted = {name for _, name, _ in _planned(role)}
        pair = next(
            (
                (first.name, second.name)
                for first in message.struct.members
                if first.name in converted
                for second in message.struct.members
                if second is not first and (second.type, second.size) == (first.type, first.size)
            ),
            None,
        )
        if pair is None:
            continue
        first, second = pair
        traded = dict(message.values)
        traded[first], traded[second] = traded[second], traded[first]
        reading = getattr(fsw, f"cdh_{role.role}")(_bus_bytes(message, pair))
        assert reading == _reading(role, traded), role.role
        assert reading != _reading(role, message.values), role.role
        swapped += 1
    assert swapped


def test_bytes_too_short_for_a_bus_struct_raise_naming_the_role(
    fsw: ModuleType, bus_messages: dict[str, Any]
) -> None:
    """A role's bytes one short of its bus struct fail F´'s deserialization, naming the role.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
    """
    for role in _roles():
        short = serialize(bus_messages[role.bus].payload)[:-1]
        match = rf"cdh_{role.role}: deserializing {re.escape(role.bus)} failed"
        with pytest.raises(RuntimeError, match=match):
            getattr(fsw, f"cdh_{role.role}")(short)
