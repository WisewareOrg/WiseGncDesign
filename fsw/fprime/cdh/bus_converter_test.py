"""The generated `Cdh.BusConverter` converts each role's struct in F´ as the Python build does.

Through each role's test pin `cdh_<role>`. For a sensor: the bus emulator's bytes for the role's
message, deserialized by F´, converted by the generated conversion and serialized back, compared
with the GNC struct `fsw.codegen.fields.plan` takes from the same values. For an actuator: a GNC
struct's bytes, packed by numpy, converted by F´ and read back by the bus emulator, compared with
the payload the Python build's CDH-out and RIO-out make of the same struct. Each test ranges over
every role of its direction the contract's `Cdh.BusConverter` declares. Skipped without the
deployment `just fsw` builds, as the `fsw` fixture skips.
"""

from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

import numpy as np

from fsw.codegen.deployment import contract_model
from fsw.codegen.fields import form, plan
from fsw.codegen.roles import Role, roles
from lab.bus_emulator import deserialize, serialize


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
    model = contract_model()
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


def _roles(sensor: bool) -> list[Role]:
    """Every role of one direction the contract's `Cdh.BusConverter` declares, at least one.

    Args:
        sensor: whether the sensor roles, else the actuator roles.

    Returns:
        The roles.
    """
    found = [role for role in roles(contract_model()) if role.sensor == sensor]
    assert found
    return found


def _icd_bytes(message: Any) -> bytes:
    """A GNC struct's value serialized as F´ does, by numpy rather than F´.

    Args:
        message: the `IcdMessage`.

    Returns:
        The bytes.
    """
    return _bytes([(np.asarray(v).dtype, v) for v in message.values.values()])


def test_each_role_s_bus_struct_converts_to_its_gnc_struct(
    fsw: ModuleType, bus_messages: dict[str, Any]
) -> None:
    """Each role's pin gives the GNC struct the field rule takes from the emulator's bytes.

    Args:
        fsw: a copy of the deployment.
        bus_messages: a message of each bus struct.
    """
    for role in _roles(sensor=True):
        message = bus_messages[role.bus]
        converted = getattr(fsw, f"cdh_{role.role}")(serialize(message.payload))
        assert converted == _reading(role, message.values), role.role


def test_each_actuator_role_s_gnc_struct_converts_to_the_payload_the_python_build_makes(
    fsw: ModuleType,
    icd_messages: dict[str, Any],
    python_command: Callable[[Role, Any], Any],
    holds: Callable[[Any, Mapping[str, Any]], None],
) -> None:
    """F´'s conversion, read back by the emulator, is the payload the Python build's CDH makes.

    The GNC struct's bytes are packed by numpy, big-endian, each element with its own value, so a
    misplaced field or byte order shows.

    Args:
        fsw: a copy of the deployment.
        icd_messages: a value of each GNC struct, its members' values distinct.
        python_command: gives the Python build's command for a role.
        holds: asserts a payload holds values.
    """
    for role in _roles(sensor=False):
        message = icd_messages[role.icd]
        python = python_command(role, message.value)
        converted = deserialize(role.bus, getattr(fsw, f"cdh_{role.role}")(_icd_bytes(message)))
        fields = type(python).__dtype__.names
        assert type(converted) is type(python), role.role
        holds(converted, {field: getattr(python, field) for field in fields})
