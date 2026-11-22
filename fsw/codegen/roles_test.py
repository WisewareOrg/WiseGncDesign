"""`Cdh.BusConverter`'s roles: each input paired with its output, the bus-typed end its direction.

The `roles` tests read a mock model of two roles, so none needs the F´ framework clone. The `taken`
tests render mock configurations of the contract's roles, on a mock device taking each.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from fsw.codegen.deployment import Contract, configuration_model, contract_model
from fsw.codegen.fpp_model import Model
from fsw.codegen.roles import Role, roles, taken
from fsw.mock import device, sub_topology

DECLARED = roles(contract_model())
"""Every role the contract declares."""

SENSORS = [role for role in DECLARED if role.sensor]
"""Every sensor role."""

ACTUATORS = [role for role in DECLARED if not role.sensor]
"""Every actuator role."""


def test_each_bus_typed_input_is_a_sensor_role_paired_with_its_output(
    converter_mock: Callable[..., Model],
) -> None:
    """The mock's two input ports give two sensor roles, each with its structs and ports.

    Args:
        converter_mock: reads the mock, edited.
    """
    assert roles(converter_mock()) == [
        Role("a", "Bus.A", "Gnc.AIcd", "aIn", "aOut", True),
        Role("b", "Bus.B", "Gnc.BIcd", "bIn", "bOut", True),
    ]


def test_a_gnc_typed_input_with_a_bus_typed_output_is_an_actuator_role(
    converter_mock: Callable[..., Model],
) -> None:
    """`cIn` taking a GNC struct and `cOut` sending a bus struct is an actuator: ICD to bus.

    `bus` and `icd` keep their meaning: the bus struct is the output's, the ICD struct the input's.

    Args:
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(
        (
            "    output port bOut: Gnc.BIcd\n",
            "    output port bOut: Gnc.BIcd\n"
            "    sync input port cIn: Gnc.BIcd\n"
            "    output port cOut: Bus.B\n",
        )
    )
    assert roles(model)[2] == Role("c", "Bus.B", "Gnc.BIcd", "cIn", "cOut", False)


def test_a_role_without_its_output_is_refused_by_name(converter_mock: Callable[..., Model]) -> None:
    """A bus-typed `bIn` with no `bOut` raises, naming the role.

    Args:
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(("    output port bOut: Gnc.BIcd\n", ""))
    with pytest.raises(ValueError, match="role b has bIn but no bOut"):
        roles(model)


@pytest.mark.parametrize(
    ("edit", "carried"),
    [
        (("output port bOut: Gnc.BIcd", "output port bOut: Bus.B"), "both carry"),
        (("sync input port bIn: Bus.B", "sync input port bIn: Gnc.BIcd"), "neither carries"),
    ],
    ids=["both-bus", "neither-bus"],
)
def test_a_role_whose_ends_do_not_say_its_direction_is_refused_by_name(
    converter_mock: Callable[..., Model], edit: tuple[str, str], carried: str
) -> None:
    """A role is a sensor or an actuator only when exactly one of its ports carries a bus struct.

    Args:
        converter_mock: reads the mock, edited.
        edit: the edit giving role b both ends, or neither, typed by a bus struct.
        carried: what the refusal says of its ends.
    """
    with pytest.raises(ValueError, match=f"role b's bIn and bOut {carried} a bus struct"):
        roles(converter_mock(edit))


def _taking(directory: Path, name: str, ports: Sequence[str]) -> Model:
    """A mock configuration's model: a device of every declared role, exposing the ports given.

    Args:
        directory: where the device and the configuration are written.
        name: the configuration.
        ports: each sub-topology port's declaration beside `tickIn`.

    Returns:
        The model.
    """
    (directory / "gnc").mkdir(exist_ok=True)
    fpp = directory / "Device.fpp"
    fpp.write_text(device("Device", DECLARED))
    (directory / "gnc" / f"{name}.fpp").write_text(
        sub_topology(name, [("device", "MockGnc.Device")], ports)
    )
    return configuration_model(name, contract=Contract((fpp,), directory / "gnc"))


def _exposed(role: Role) -> str:
    """The sub-topology port a configuration takes a role at.

    Args:
        role: the role.

    Returns:
        `port <role>In = device.<role>In` for a sensor, `port <role>Out = device.<role>Out` for an
        actuator.
    """
    port = role.input if role.sensor else role.output
    return f"port {port} = device.{port}"


@pytest.mark.parametrize(
    "exposed",
    [DECLARED, SENSORS, ACTUATORS, []],
    ids=["every-role", "sensors-only", "actuators-only", "no-role"],
)
def test_a_configuration_takes_the_roles_its_sub_topology_exposes_in_converter_order(
    tmp_path: Path, exposed: list[Role]
) -> None:
    """A sensor at its `<role>In` on an input, an actuator at its `<role>Out` on an output.

    Args:
        tmp_path: where the mock is written.
        exposed: the roles the sub-topology exposes.
    """
    assert SENSORS and ACTUATORS
    model = _taking(tmp_path, "Taking", [_exposed(role) for role in reversed(exposed)])

    assert taken(model, "Taking") == tuple(exposed)


@pytest.mark.parametrize(
    ("port", "named"),
    [
        (f"port {SENSORS[0].input} = device.{ACTUATORS[0].output}", "actuator"),
        (f"port {ACTUATORS[0].output} = device.{SENSORS[0].input}", "sensor"),
        (f"port notARoleIn = device.{SENSORS[0].input}", "sensor"),
    ],
    ids=["sensor-name-on-an-output", "actuator-name-on-an-input", "no-role-s-name"],
)
def test_a_port_that_names_no_role_in_its_direction_is_refused_naming_it(
    tmp_path: Path, port: str, named: str
) -> None:
    """A sub-topology port whose name is no role's in the direction of the port it exposes.

    Args:
        tmp_path: where the mock is written.
        port: the port's declaration.
        named: the direction of the instance port it exposes, as the refusal names it.
    """
    model = _taking(tmp_path, "Refused", [port])
    short = port.split()[1]

    with pytest.raises(ValueError, match=rf"port {short}, an instance's .*, names no {named} role"):
        taken(model, "Refused")
