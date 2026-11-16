"""The F´ CDH generator: its roles from `Cdh.BusConverter`'s ports, and the C++ it emits for them.

Each test but the contract's reads a toy model, two roles whose structs exercise the field rule,
so none needs the F´ framework clone.
"""

from pathlib import Path

import pytest

from fsw.codegen.bus_converter import Role, main, render, roles
from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import Model, read

TOY = """\
module Bus {
  struct A { x: F64, extra: U32, v: [3] F64 }
  port A(msg: A)
  struct B { n: I16 }
  port B(msg: B)
}
module Gnc {
  enum Mode {
    standby
    running
  }
  array Row = [3] F64
  array Mat = [2] Row
  struct AIcd { X: F64, v: Row }
  port AIcd(reading: AIcd)
  struct BIcd { n: I16 }
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
"""Role `a` takes a scalar by another case, a 1-D array and drops `extra`; role `b` a scalar of
another type. `Mode` and `Mat` are there for the edits that seed a refusal."""


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


def test_two_roles_emit_two_handlers(tmp_path: Path) -> None:
    """The component declares and defines a handler per role, each sending on its output.

    Args:
        tmp_path: where the toy is written.
    """
    files = render(_toy(tmp_path))
    for role, bus in (("a", "Bus::A"), ("b", "Bus::B")):
        signature = f"{role}In_handler(FwIndexType, const {bus}& bus)"
        assert f"void {signature} override;" in files["BusConverter.hpp"]
        assert f"void BusConverter::{signature} {{" in files["BusConverter.cpp"]
        assert f"this->{role}Out_out(0, icd);" in files["BusConverter.cpp"]


def test_each_field_is_copied_from_the_bus_field_of_its_name_and_extras_are_dropped(
    tmp_path: Path,
) -> None:
    """A scalar is set from its namesake in another case, an array copied; `extra` is not read.

    Args:
        tmp_path: where the toy is written.
    """
    source = render(_toy(tmp_path))["BusConverter.cpp"]
    assert "icd.set_X(bus.get_x());" in source
    assert "icd.get_v()[i] = bus.get_v()[i];" in source
    assert "extra" not in source


def test_an_array_of_arrays_is_refused_by_name(tmp_path: Path) -> None:
    """A `Mat` matched by a bus `[2] Row` passes the field rule, but the CDH refuses it, naming it.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(
        tmp_path,
        ("struct B { n: I16 }", "struct B { m: [2] Gnc.Row }"),
        ("struct BIcd { n: I16 }", "struct BIcd { m: Mat }"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.BIcd\.m is \(2, 3\) float64, which the F´ CDH"):
        render(model)


def test_a_bool_is_refused_by_name(tmp_path: Path) -> None:
    """A `bool` matched by a bus `bool` passes the field rule, but the CDH refuses it, naming it.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(
        tmp_path,
        ("struct A { x: F64", "struct A { x: bool"),
        ("struct AIcd { X: F64", "struct AIcd { X: bool"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.X is \(\) bool, which the F´ CDH"):
        render(model)


def test_a_field_of_another_shape_is_refused_by_name(tmp_path: Path) -> None:
    """A bus `v` of four elements cannot fill the ICD's three, and raises naming the field.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(tmp_path, ("v: [3] F64", "v: [4] F64"))
    with pytest.raises(
        ValueError, match=r"Gnc\.AIcd\.v is \(3,\) float64, but Bus\.A\.v is \(4,\)"
    ):
        render(model)


def test_a_field_of_another_element_type_is_refused_by_name(tmp_path: Path) -> None:
    """A bus `x` of `F32` cannot fill the ICD's `F64` `X`, and raises naming the field.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(tmp_path, ("struct A { x: F64", "struct A { x: F32"))
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.X is \(\) float64, but Bus\.A\.x is"):
        render(model)


def test_a_field_that_is_not_a_number_is_refused_by_name(tmp_path: Path) -> None:
    """An enum field matches by the field rule, but the F´ CDH copies numbers only, naming it.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(
        tmp_path,
        ("{ x: F64, extra: U32", "{ x: Gnc.Mode, extra: U32"),
        ("struct AIcd { X: F64", "struct AIcd { X: Mode"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.X is \(\) Gnc\.Mode, which the F´ CDH"):
        render(model)


def test_each_bus_struct_a_role_takes_has_one_bus_pin(tmp_path: Path) -> None:
    """A third role on `Bus.A` adds no pin: one per bus struct, taking each member by its name.

    Args:
        tmp_path: where the toy is written.
    """
    pins = render(
        _toy(
            tmp_path,
            (
                "    sync input port bIn",
                "    sync input port cIn: Bus.A\n"
                "    output port cOut: Gnc.AIcd\n"
                "    sync input port bIn",
            ),
        )
    )["BusConverterPins.hpp"]
    assert pins.count('"bus_A"') == 1
    assert pins.count('"bus_B"') == 1
    assert "[](F64 x, U32 extra, const std::array<F64, 3>& v)" in pins
    assert 'pybind11::arg("x"), pybind11::arg("extra"), pybind11::arg("v")' in pins


def test_a_bus_member_outside_the_pin_s_domain_is_refused_by_name(tmp_path: Path) -> None:
    """A bus `bool` the CDH drops still has no bus bytes, so its pin refuses it, naming it.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(tmp_path, ("extra: U32", "extra: bool"))
    with pytest.raises(ValueError, match=r"Bus\.A\.extra is of bool, which the bus pin"):
        render(model)


def test_the_contract_pairs_the_imu_bus_message_with_the_imu_reading() -> None:
    """The real `Cdh.BusConverter` has one role, the IMU's."""
    assert roles(read(contract_files())) == [
        Role("imu", "Bus.ImuSensorMsg", "Gnc.ImuReading", "imuIn", "imuOut")
    ]


def test_the_tool_writes_the_component_into_its_directory(tmp_path: Path) -> None:
    """`python -m fsw.codegen.bus_converter <dir>` writes the component and its pins.

    Args:
        tmp_path: the directory.
    """
    main([str(tmp_path)])
    assert "class BusConverter final" in (tmp_path / "BusConverter.hpp").read_text()
    assert "imuIn_handler" in (tmp_path / "BusConverter.cpp").read_text()
    assert '"bus_ImuSensorMsg"' in (tmp_path / "BusConverterPins.hpp").read_text()
