"""The F´ CDH generator: the C++ it emits for `Cdh.BusConverter`'s roles, and what it refuses.

Each test but the tool's reads a toy model of two roles, so none needs the F´ framework clone.
"""

from pathlib import Path

import pytest

from fsw.codegen.bus_converter import main, render
from fsw.codegen.fpp_model import Model, read

TOY = """\
module Bus {
  struct A { extra: [2] F64, v: [3] F64 }
  port A(msg: A)
  struct B { n: [2] F64 }
  port B(msg: B)
}
module Gnc {
  enum Mode {
    standby
    running
  }
  array Row = [3] F64
  array Mat = [2] Row
  struct AIcd { V: Row }
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
"""Role `a` takes a 3-vector by an array type and another case, and drops `extra`; role `b` an
inline array. `Mode` and `Mat` are there for the edits that seed a refusal."""


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


def test_two_roles_emit_two_handlers_and_two_conversions(tmp_path: Path) -> None:
    """Per role, the header defines its conversion inline and the source a handler sending it.

    Args:
        tmp_path: where the toy is written.
    """
    files = render(_toy(tmp_path))
    for role, bus, icd in (("a", "Bus::A", "Gnc::AIcd"), ("b", "Bus::B", "Gnc::BIcd")):
        signature = f"{role}In_handler(FwIndexType, const {bus}& msg)"
        assert f"static {icd} convert_{role}(const {bus}& bus) {{" in files["BusConverter.hpp"]
        assert f"void {signature} override;" in files["BusConverter.hpp"]
        assert f"void BusConverter::{signature} {{" in files["BusConverter.cpp"]
        assert f"this->{role}Out_out(0, convert_{role}(msg));" in files["BusConverter.cpp"]


def test_each_field_is_copied_from_the_bus_field_of_its_name_and_extras_are_dropped(
    tmp_path: Path,
) -> None:
    """`V` is copied from `v`, another case, and `n` from `n`, each by element; `extra` is not read.

    Args:
        tmp_path: where the toy is written.
    """
    files = render(_toy(tmp_path))
    header = files["BusConverter.hpp"]
    assert "icd.get_V()[i] = bus.get_v()[i];" in header
    assert "icd.get_n()[i] = bus.get_n()[i];" in header
    assert "extra" not in header + files["BusConverter.cpp"]


def test_an_array_of_arrays_is_refused_by_name(tmp_path: Path) -> None:
    """A `Mat` matched by a bus `[2] Row` passes the field rule, but the CDH refuses it, naming it.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(
        tmp_path,
        ("struct B { n: [2] F64 }", "struct B { m: [2] Gnc.Row }"),
        ("struct BIcd { n: [2] F64 }", "struct BIcd { m: Mat }"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.BIcd\.m is \(2, 3\) float64, which the F´ CDH"):
        render(model)


def test_a_scalar_is_refused_by_name(tmp_path: Path) -> None:
    """A scalar matched by a bus scalar passes the field rule, but the CDH refuses it, naming it.

    No struct has a scalar, so the first one adds its copy with a compiled test.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(
        tmp_path,
        ("struct A { extra", "struct A { x: F64, extra"),
        ("struct AIcd { V", "struct AIcd { X: F64, V"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.X is \(\) float64, which the F´ CDH"):
        render(model)


@pytest.mark.parametrize("element", ["bool", "U32"], ids=["bool", "unused-primitive"])
def test_an_element_type_outside_the_domain_is_refused_by_name(
    element: str, tmp_path: Path
) -> None:
    """A `bool` array, or one of a primitive no struct uses, passes the field rule but is refused.

    Args:
        element: the arrays' element type.
        tmp_path: where the toy is written.
    """
    model = _toy(
        tmp_path,
        ("struct A { extra", f"struct A {{ f: [2] {element}, extra"),
        ("struct AIcd { V", f"struct AIcd {{ f: [2] {element}, V"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.f is \(2,\) \w+, which the F´ CDH"):
        render(model)


def test_a_field_that_is_not_a_number_is_refused_by_name(tmp_path: Path) -> None:
    """An enum array matches by the field rule, but the F´ CDH copies numbers only, naming it.

    Args:
        tmp_path: where the toy is written.
    """
    model = _toy(
        tmp_path,
        ("struct A { extra", "struct A { e: [2] Gnc.Mode, extra"),
        ("struct AIcd { V", "struct AIcd { e: [2] Mode, V"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.e is \(2,\) Gnc\.Mode, which the F´ CDH"):
        render(model)


def test_each_role_has_a_cdh_pin_and_each_bus_struct_one_bus_pin(tmp_path: Path) -> None:
    """A third role on `Bus.A` adds a CDH pin but no bus pin, which is one per bus struct.

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
    for role, bus in (("a", "Bus::A"), ("c", "Bus::A"), ("b", "Bus::B")):
        assert f'"cdh_{role}"' in pins
        assert f"{bus} msg;" in pins
        assert f"Cdh::BusConverter::convert_{role}(msg)" in pins
    assert "[](const std::array<F64, 2>& extra, const std::array<F64, 3>& v)" in pins
    assert 'pybind11::arg("extra"), pybind11::arg("v")' in pins


@pytest.mark.parametrize(
    ("extra", "named"),
    [
        ("extra: F64", "extra is F64"),
        ("extra: [2] bool", r"extra is \[2\] bool"),
        ("extra: [2] U32", r"extra is \[2\] U32"),
    ],
    ids=["scalar", "bool", "unused-primitive"],
)
def test_a_bus_member_outside_the_pin_s_domain_is_refused_by_name(
    extra: str, named: str, tmp_path: Path
) -> None:
    """A bus scalar, `bool` or primitive no struct uses, dropped by the CDH, is refused by the pin.

    Args:
        extra: the member as the seeded toy declares it.
        named: the member as the refusal names it, a pattern.
        tmp_path: where the toy is written.
    """
    model = _toy(tmp_path, ("extra: [2] F64", extra))
    with pytest.raises(ValueError, match=rf"Bus\.A\.{named}, which the bus pin"):
        render(model)


def test_the_tool_writes_the_component_into_its_directory(tmp_path: Path) -> None:
    """`python -m fsw.codegen.bus_converter <dir>` writes the component and its pins.

    Args:
        tmp_path: the directory.
    """
    main([str(tmp_path)])
    assert "class BusConverter final" in (tmp_path / "BusConverter.hpp").read_text()
    assert "imuIn_handler" in (tmp_path / "BusConverter.cpp").read_text()
    assert '"bus_ImuSensorMsg"' in (tmp_path / "BusConverterPins.hpp").read_text()
