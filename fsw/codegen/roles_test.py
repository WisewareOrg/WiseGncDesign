"""`Cdh.BusConverter`'s roles: each input paired with its output, the bus-typed end its direction.

Each test reads a mock model of two roles, so none needs the F´ framework clone.
"""

from collections.abc import Callable

import pytest

from fsw.codegen.fpp_model import Model
from fsw.codegen.roles import Role, roles


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
