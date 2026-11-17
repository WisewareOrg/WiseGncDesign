"""The Python build's CDH-in pairs each sensor role from FPP and converts its bus struct to ICD.

Each configuration's pairing is read from the contract and its sub-topology, every algorithm a
class named for its component; the refusals are read from a mock converter, built from the
contract's first role; the conversion ranges over every role, on `bus_messages`' values.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.codegen import fpp_types
from fsw.codegen.deployment import (
    algorithm_components,
    configuration_model,
    contract_files,
    framework_files,
)
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.roles import roles
from fsw.python.cdh.inputs import Pair, convert, pairings
from fsw.python.gnc.partition import GncPartition

_REPOSITORY = Path(__file__).resolve().parents[3]

ROLES = roles(read(contract_files()))
"""Every role of the contract's `Cdh.BusConverter`."""

ROLE = ROLES[0]
"""The role the mock converter carries."""

CDH = f"""\
module Cdh {{
  passive component BusConverter {{
    sync input port {ROLE.input}: {ROLE.bus}
    output port {ROLE.output}: {ROLE.icd}
  }}
}}
"""
"""A mock converter of the contract's first role alone."""


def _model(directory: Path, cdh: str = CDH) -> Model:
    """A mock converter's model, with the framework and the interfaces.

    Args:
        directory: where `Cdh.fpp` is written.
        cdh: the converter's FPP.

    Returns:
        The model.
    """
    (directory / "Cdh.fpp").write_text(cdh)
    interfaces = _REPOSITORY / "fsw" / "fpp" / "interfaces"
    return read(
        [
            *framework_files(),
            interfaces / "Bus.fpp",
            interfaces / "Interfaces.fpp",
            directory / "Cdh.fpp",
        ]
    )


def _algorithm_classes(model: Model, configuration: str) -> list[type]:
    """An empty class per algorithm component the configuration instances, named for it.

    Args:
        model: the configuration's model.
        configuration: the configuration.

    Returns:
        The classes.
    """
    components = {
        instance.component
        for name, instance in model.instances.items()
        if name.startswith(f"{configuration}.") and instance.component in algorithm_components()
    }
    return [type(component.rsplit(".", 1)[-1], (), {}) for component in sorted(components)]


def test_each_configuration_pairs_every_input_to_the_struct_its_gnc_port_takes(
    configuration: str,
):
    """Each sub-topology input is a role's, from its bus struct to the type the GNC port takes.

    Args:
        configuration: the configuration.
    """
    model = configuration_model(configuration)
    inputs = GncPartition(model, configuration, _algorithm_classes(model, configuration)).inputs
    assert inputs

    pairs = pairings(model, inputs)

    assert {pair.port for pair in pairs} == set(inputs)
    bus = {role.input: role.bus for role in roles(model)}
    for pair in pairs:
        port = model.ports[f"{configuration}.Gnc.{pair.port}"]
        component = model.components[model.instances[port.instance].component]
        [taken] = [p for p in component.inputs if p.name == port.port]
        assert pair.role == pair.port.removesuffix("In"), pair.port
        assert pair.bus is fpp_types.named(bus[pair.port]), pair.port
        assert pair.icd is fpp_types.named(taken.args[0].type), pair.port


def test_a_role_the_sub_topology_does_not_take_is_skipped(tmp_path: Path):
    """A converter role with no sub-topology input of its name is not paired.

    Args:
        tmp_path: where the mock is written.
    """
    assert pairings(_model(tmp_path), ()) == []


def test_a_role_without_its_output_is_refused_naming_it(tmp_path: Path):
    """Each bus-typed `<role>In` needs `<role>Out`, which the GNC's type is carried on.

    Args:
        tmp_path: where the mock is written.
    """
    cdh = CDH.replace(f"output port {ROLE.output}:", "output port notAnOut:")

    with pytest.raises(ValueError, match=f"role {ROLE.role}"):
        pairings(_model(tmp_path, cdh=cdh), (ROLE.input,))


def test_a_role_whose_output_is_a_bus_struct_is_refused_naming_it(tmp_path: Path):
    """A bus-typed input converts to the GNC's type, never to another bus struct.

    Args:
        tmp_path: where the mock is written.
    """
    cdh = CDH.replace(
        f"output port {ROLE.output}: {ROLE.icd}", f"output port {ROLE.output}: {ROLE.bus}"
    )

    with pytest.raises(ValueError, match=f"role {ROLE.role}"):
        pairings(_model(tmp_path, cdh=cdh), (ROLE.input,))


def test_a_sub_topology_input_no_role_feeds_is_refused_naming_it(tmp_path: Path):
    """A data input of the sub-topology with no converter pair would never be written.

    Args:
        tmp_path: where the mock is written.
    """
    with pytest.raises(ValueError, match=r"\['notARoleIn'\]"):
        pairings(_model(tmp_path), (ROLE.input, "notARoleIn"))


def test_each_role_s_bus_struct_is_converted_to_its_icd_struct_at_its_gnc_port(
    bus_messages: dict[str, Any],
):
    """Each role's bus struct reaches its port as a fresh ICD struct, each field its namesake's.

    The ICD struct takes each field from the bus member of its name, ignoring case, by
    `fsw.codegen.fields`' rule; the bus struct changed afterwards leaves it as it was.

    Args:
        bus_messages: a message of each bus struct, its members' values distinct.
    """
    pairs = [
        Pair(role.role, fpp_types.named(role.bus), fpp_types.named(role.icd), role.input)
        for role in ROLES
    ]
    messages = {
        pair.role: pair.bus(**{m: np.array(v) for m, v in bus_messages[role.bus].values.items()})
        for pair, role in zip(pairs, ROLES, strict=True)
    }

    converted = convert(pairs, messages)
    for message in messages.values():
        for value in message:
            value[...] = 0

    assert list(converted) == [pair.port for pair in pairs]
    for pair, role in zip(pairs, ROLES, strict=True):
        reading = converted[pair.port]
        assert isinstance(reading, pair.icd), pair.port
        values = {m.lower(): v for m, v in bus_messages[role.bus].values.items()}
        for field in reading._fields:
            np.testing.assert_array_equal(getattr(reading, field), values[field.lower()])
