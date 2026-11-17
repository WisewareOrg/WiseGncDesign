"""The F´ CDH generator: the C++ it emits for `Cdh.BusConverter`'s roles, and what it refuses.

Each test but the tool's reads a mock model of two roles, so none needs the F´ framework clone.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from fsw.codegen.bus_converter import main, render
from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.roles import roles


def test_two_roles_emit_two_handlers_and_two_conversions(
    converter_mock: Callable[..., Model],
) -> None:
    """Per role, the header defines its conversion inline and the source a handler sending it.

    Args:
        converter_mock: reads the mock, edited.
    """
    files = render(converter_mock())
    for role, bus, icd in (("a", "Bus::A", "Gnc::AIcd"), ("b", "Bus::B", "Gnc::BIcd")):
        signature = f"{role}In_handler(FwIndexType, const {bus}& msg)"
        assert f"static {icd} convert_{role}(const {bus}& bus) {{" in files["BusConverter.hpp"]
        assert f"void {signature} override;" in files["BusConverter.hpp"]
        assert f"void BusConverter::{signature} {{" in files["BusConverter.cpp"]
        assert f"this->{role}Out_out(0, convert_{role}(msg));" in files["BusConverter.cpp"]


def test_each_field_is_copied_from_the_bus_field_of_its_name_and_extras_are_dropped(
    converter_mock: Callable[..., Model],
) -> None:
    """`V` is copied from `v`, another case, and `n` from `n`, each by element; `extra` is not read.

    Args:
        converter_mock: reads the mock, edited.
    """
    files = render(converter_mock())
    header = files["BusConverter.hpp"]
    assert "icd.get_V()[i] = bus.get_v()[i];" in header
    assert "icd.get_n()[i] = bus.get_n()[i];" in header
    assert "extra" not in header + files["BusConverter.cpp"]


def test_each_role_has_a_cdh_pin_and_each_bus_struct_one_bus_pin(
    converter_mock: Callable[..., Model],
) -> None:
    """A third role on `Bus.A` adds a CDH pin but no bus pin, which is one per bus struct.

    Args:
        converter_mock: reads the mock, edited.
    """
    pins = render(
        converter_mock(
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
    ("edits", "match"),
    [
        (
            (
                ("struct B { n: [2] F64 }", "struct B { m: [2] Gnc.Row }"),
                ("struct BIcd { n: [2] F64 }", "struct BIcd { m: Mat }"),
            ),
            r"Gnc\.BIcd\.m is \(2, 3\) float64, which the F´ CDH",
        ),
        (
            (
                ("struct A { extra", "struct A { x: F64, extra"),
                ("struct AIcd { V", "struct AIcd { X: F64, V"),
            ),
            r"Gnc\.AIcd\.X is \(\) float64, which the F´ CDH",
        ),
        (
            (
                ("struct A { extra", "struct A { f: [2] bool, extra"),
                ("struct AIcd { V", "struct AIcd { f: [2] bool, V"),
            ),
            r"Gnc\.AIcd\.f is \(2,\) bool, which the F´ CDH",
        ),
        (
            (
                ("struct A { extra", "struct A { f: [2] U32, extra"),
                ("struct AIcd { V", "struct AIcd { f: [2] U32, V"),
            ),
            r"Gnc\.AIcd\.f is \(2,\) uint32, which the F´ CDH",
        ),
        (
            (
                ("struct A { extra", "struct A { e: [2] Gnc.Mode, extra"),
                ("struct AIcd { V", "struct AIcd { e: [2] Mode, V"),
            ),
            r"Gnc\.AIcd\.e is \(2,\) Gnc\.Mode, which the F´ CDH",
        ),
        ((("extra: [2] F64", "extra: F64"),), r"Bus\.A\.extra is F64, which the bus pin"),
        (
            (("extra: [2] F64", "extra: [2] bool"),),
            r"Bus\.A\.extra is \[2\] bool, which the bus pin",
        ),
        (
            (("extra: [2] F64", "extra: [2] U32"),),
            r"Bus\.A\.extra is \[2\] U32, which the bus pin",
        ),
    ],
    ids=[
        "array-of-arrays",
        "scalar",
        "bool",
        "unused-primitive",
        "not-a-number",
        "bus-scalar",
        "bus-bool",
        "bus-unused-primitive",
    ],
)
def test_a_field_outside_the_domain_is_refused_by_name(
    converter_mock: Callable[..., Model], edits: tuple[tuple[str, str], ...], match: str
) -> None:
    """A field the field rule passes but the F´ CDH or the bus pin cannot copy is refused, named.

    The CDH copies arrays of numbers its structs use: an array of arrays, a scalar, a `bool` array,
    one of a primitive no struct uses, and an enum array are refused. No struct has a scalar, so the
    first one adds its copy with a compiled test. The bus pin refuses a bus member the CDH drops
    that is a scalar, a `bool` array or one of a primitive no struct uses.

    Args:
        converter_mock: reads the mock, edited.
        edits: the mock's edits.
        match: the refusal, naming the field.
    """
    model = converter_mock(*edits)
    with pytest.raises(ValueError, match=match):
        render(model)


def test_the_tool_writes_the_component_and_its_pins_for_every_role(tmp_path: Path) -> None:
    """`python -m fsw.codegen.bus_converter <dir>` writes a handler and pins per contract role.

    Args:
        tmp_path: the directory.
    """
    main([str(tmp_path)])
    found = roles(read(contract_files()))
    assert found
    assert "class BusConverter final" in (tmp_path / "BusConverter.hpp").read_text()
    source = (tmp_path / "BusConverter.cpp").read_text()
    pins = (tmp_path / "BusConverterPins.hpp").read_text()
    for role in found:
        assert f"void BusConverter::{role.input}_handler(" in source
        assert f'"cdh_{role.role}"' in pins
        assert f'"bus_{role.bus.removeprefix("Bus.")}"' in pins
