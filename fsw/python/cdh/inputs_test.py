"""The Python build's CDH-in pairs each sensor role from FPP and converts its bus struct to ICD.

Each configuration's pairing is of the sensor roles it takes, read from the contract and its
sub-topology; the conversion ranges over every sensor role, on `bus_messages`' values.
"""

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import pytest

from fsw.codegen import fpp_types
from fsw.codegen.deployment import (
    configuration_model,
    contract_model,
)
from fsw.codegen.roles import roles, taken
from fsw.python.cdh.inputs import converter, pairings

ROLES = [role for role in roles(contract_model()) if role.sensor]
"""Every sensor role of the contract's `Cdh.BusConverter`."""


def test_each_configuration_pairs_each_sensor_role_to_the_struct_its_gnc_port_takes(
    configuration: str,
):
    """Each sensor role taken is paired from its bus struct to the type its GNC port takes.

    Args:
        configuration: the configuration.
    """
    model = configuration_model(configuration)
    pairs = pairings([role for role in taken(model, configuration) if role.sensor])
    if not pairs:
        pytest.skip(f"{configuration} takes no sensor role")

    bus = {role.input: role.bus for role in roles(model)}
    for pair in pairs:
        port = model.ports[f"{configuration}.Gnc.{pair.port}"]
        component = model.components[model.instances[port.instance].component]
        [instance_port] = [p for p in component.inputs if p.name == port.port]
        assert pair.role == pair.port.removesuffix("In"), pair.port
        assert pair.bus is fpp_types.named(bus[pair.port]), pair.port
        assert pair.icd is fpp_types.named(instance_port.args[0].type), pair.port


def test_each_role_s_bus_struct_is_converted_to_its_icd_struct_at_its_gnc_port(
    bus_messages: dict[str, Any], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """Each role's bus struct reaches its port as an ICD struct holding the bus struct's arrays.

    The ICD struct takes each field from the bus member of its name, ignoring case, by
    `fsw.codegen.fields`' rule. RIO-in's arrays are fresh and read-only, so CDH-in passes them
    through, as `GncPartition` passes an output to the member it is routed to.

    Args:
        bus_messages: a message of each bus struct, its members' values distinct.
        holds: asserts a tuple holds values.
    """
    pairs = pairings(ROLES)
    messages = {
        pair.role: pair.bus(**{m: np.array(v) for m, v in bus_messages[role.bus].values.items()})
        for pair, role in zip(pairs, ROLES, strict=True)
    }

    for pair, role in zip(pairs, ROLES, strict=True):
        reading = converter(pair)(messages[pair.role])

        assert isinstance(reading, pair.icd), pair.port
        holds(reading, bus_messages[role.bus].values)
        bus = messages[pair.role]
        for field in reading._fields:
            same = next(m for m in bus._fields if m.lower() == field.lower())
            assert getattr(reading, field) is getattr(bus, same), f"{pair.port}.{field} was copied"
