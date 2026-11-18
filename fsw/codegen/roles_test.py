"""`Cdh.BusConverter`'s roles: each bus-typed input, paired with its GNC output.

Each test reads a mock model of two roles, so none needs the F´ framework clone.
"""

from collections.abc import Callable

import pytest

from fsw.codegen.fpp_model import Model
from fsw.codegen.roles import Role, roles


def test_each_bus_typed_input_is_a_role_paired_with_its_output(
    converter_mock: Callable[..., Model],
) -> None:
    """The mock's two input ports give two roles, each with its bus and ICD structs and ports.

    Args:
        converter_mock: reads the mock, edited.
    """
    assert roles(converter_mock()) == [
        Role("a", "Bus.A", "Gnc.AIcd", "aIn", "aOut"),
        Role("b", "Bus.B", "Gnc.BIcd", "bIn", "bOut"),
    ]


def test_a_role_without_its_output_is_refused_by_name(converter_mock: Callable[..., Model]) -> None:
    """A bus-typed `bIn` with no `bOut` raises, naming the role.

    Args:
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(("    output port bOut: Gnc.BIcd\n", ""))
    with pytest.raises(ValueError, match="role b takes Bus.B at bIn but has no bOut"):
        roles(model)


def test_a_role_whose_output_carries_a_bus_struct_is_refused_by_name(
    converter_mock: Callable[..., Model],
) -> None:
    """A `bOut` typed by a bus struct is no GNC output, and raises naming the role.

    Args:
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(("output port bOut: Gnc.BIcd", "output port bOut: Bus.B"))
    with pytest.raises(ValueError, match="role b takes Bus.B at bIn but has no bOut of a GNC type"):
        roles(model)
