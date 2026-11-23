"""The Python build's CDH-out pairs each actuator role from FPP and converts its ICD struct to bus.

The conversion ranges over every actuator role the contract declares, on `icd_messages`' values.
"""

from collections.abc import Callable, Mapping
from typing import Any

from fsw.codegen import fpp_types
from fsw.codegen.deployment import contract_model
from fsw.codegen.roles import roles
from fsw.python.cdh.outputs import converter, pairings

ACTUATORS = [role for role in roles(contract_model()) if not role.sensor]
"""Every actuator role of the contract's `Cdh.BusConverter`."""


def test_each_role_s_icd_struct_written_at_its_gnc_port_is_converted_to_its_bus_struct(
    icd_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """Each GNC output becomes a bus struct holding the ICD struct's arrays, each its namesake's.

    The bus struct takes each field from the ICD member of its name, ignoring case, by
    `fsw.codegen.fields`' rule, uncopied: RIO-out copies it into the payload in the same tick.

    Args:
        icd_messages: a value of each ICD struct, its members' values distinct.
        holds: asserts a tuple holds values.
    """
    assert ACTUATORS
    pairs = pairings(ACTUATORS)
    written = {pair.port: icd_messages[role.icd].value for pair, role in zip(pairs, ACTUATORS, strict=True)}

    for pair, role in zip(pairs, ACTUATORS, strict=True):
        bus = converter(pair)(written[pair.port])

        assert isinstance(bus, fpp_types.named(role.bus)), role.role
        holds(bus, icd_messages[role.icd].values)
        icd = written[pair.port]
        for field in bus._fields:
            same = next(m for m in icd._fields if m.lower() == field.lower())
            assert getattr(bus, field) is getattr(icd, same), f"{role.role}.{field} was copied"
