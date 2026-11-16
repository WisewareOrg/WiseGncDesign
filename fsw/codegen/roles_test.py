"""`Cdh.BusConverter`'s roles: each bus-typed input, paired with its GNC output.

Each test but the contract's reads a toy model of two roles, so none needs the F´ framework clone.
"""

from pathlib import Path

import pytest

from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.roles import Role, roles

TOY = """\
module Bus {
  struct A { v: [3] F64 }
  port A(msg: A)
  struct B { n: [2] F64 }
  port B(msg: B)
}
module Gnc {
  struct AIcd { v: [3] F64 }
  port AIcd(reading: AIcd)
  struct BIcd { n: [2] F64 }
  port BIcd(reading: BIcd)
}
module Cdh {
  passive component BusConverter {
    sync input port aIn: Bus.A
    output port aOut: Gnc.AIcd
    sync input port bIn: Bus.B
    output port bOut: Gnc.BIcd
  }
}
"""
"""Two roles, `a` and `b`, each a bus struct's input paired with a GNC struct's output."""


def _toy(tmp_path: Path, *edits: tuple[str, str]) -> Model:
    """The toy model, each edit's old text replaced by its new once it is seen to change the toy.

    Args:
        tmp_path: where the toy's file is written.
        *edits: each `(old, new)` replacement; none leaves the toy as it is.

    Returns:
        The model.
    """
    text = TOY
    for old, new in edits:
        edited = text.replace(old, new)
        assert edited != text, old
        text = edited
    path = tmp_path / "Toy.fpp"
    path.write_text(text)
    return read([path])


def test_each_bus_typed_input_is_a_role_paired_with_its_output(tmp_path: Path) -> None:
    """The toy's two input ports give two roles, each with its bus and ICD structs and ports.

    Args:
        tmp_path: where the toy is written.
    """
    assert roles(_toy(tmp_path)) == [
        Role("a", "Bus.A", "Gnc.AIcd", "aIn", "aOut"),
        Role("b", "Bus.B", "Gnc.BIcd", "bIn", "bOut"),
    ]


def test_a_role_without_its_output_is_refused_by_name(tmp_path: Path) -> None:
    """A bus-typed `bIn` with no `bOut` raises, naming the role.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(tmp_path, ("    output port bOut: Gnc.BIcd\n", ""))
    with pytest.raises(ValueError, match="role b takes Bus.B at bIn but has no bOut"):
        roles(model)


def test_a_role_whose_output_carries_a_bus_struct_is_refused_by_name(tmp_path: Path) -> None:
    """A `bOut` typed by a bus struct is no GNC output, and raises naming the role.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(tmp_path, ("output port bOut: Gnc.BIcd", "output port bOut: Bus.B"))
    with pytest.raises(ValueError, match="role b takes Bus.B at bIn but has no bOut of a GNC type"):
        roles(model)


def test_the_contract_pairs_the_imu_bus_message_with_the_imu_reading() -> None:
    """The real `Cdh.BusConverter` has one role, the IMU's."""
    assert roles(read(contract_files())) == [
        Role("imu", "Bus.ImuSensorMsg", "Gnc.ImuReading", "imuIn", "imuOut")
    ]
