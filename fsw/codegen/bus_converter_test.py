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


def test_an_array_of_arrays_is_refused_by_name(converter_mock: Callable[..., Model]) -> None:
    """A `Mat` matched by a bus `[2] Row` passes the field rule, but the CDH refuses it, naming it.

    Args:
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(
        ("struct B { n: [2] F64 }", "struct B { m: [2] Gnc.Row }"),
        ("struct BIcd { n: [2] F64 }", "struct BIcd { m: Mat }"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.BIcd\.m is \(2, 3\) float64, which the F´ CDH"):
        render(model)


def test_a_scalar_is_refused_by_name(converter_mock: Callable[..., Model]) -> None:
    """A scalar matched by a bus scalar passes the field rule, but the CDH refuses it, naming it.

    No struct has a scalar, so the first one adds its copy with a compiled test.

    Args:
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(
        ("struct A { extra", "struct A { x: F64, extra"),
        ("struct AIcd { V", "struct AIcd { X: F64, V"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.X is \(\) float64, which the F´ CDH"):
        render(model)


@pytest.mark.parametrize("element", ["bool", "U32"], ids=["bool", "unused-primitive"])
def test_an_element_type_outside_the_domain_is_refused_by_name(
    element: str, converter_mock: Callable[..., Model]
) -> None:
    """A `bool` array, or one of a primitive no struct uses, passes the field rule but is refused.

    Args:
        element: the arrays' element type.
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(
        ("struct A { extra", f"struct A {{ f: [2] {element}, extra"),
        ("struct AIcd { V", f"struct AIcd {{ f: [2] {element}, V"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.f is \(2,\) \w+, which the F´ CDH"):
        render(model)


def test_a_field_that_is_not_a_number_is_refused_by_name(
    converter_mock: Callable[..., Model],
) -> None:
    """An enum array matches by the field rule, but the F´ CDH copies numbers only, naming it.

    Args:
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(
        ("struct A { extra", "struct A { e: [2] Gnc.Mode, extra"),
        ("struct AIcd { V", "struct AIcd { e: [2] Mode, V"),
    )
    with pytest.raises(ValueError, match=r"Gnc\.AIcd\.e is \(2,\) Gnc\.Mode, which the F´ CDH"):
        render(model)


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
    ("extra", "named"),
    [
        ("extra: F64", "extra is F64"),
        ("extra: [2] bool", r"extra is \[2\] bool"),
        ("extra: [2] U32", r"extra is \[2\] U32"),
    ],
    ids=["scalar", "bool", "unused-primitive"],
)
def test_a_bus_member_outside_the_pin_s_domain_is_refused_by_name(
    extra: str, named: str, converter_mock: Callable[..., Model]
) -> None:
    """A bus scalar, `bool` or primitive no struct uses, dropped by the CDH, is refused by the pin.

    Args:
        extra: the member as the seeded mock declares it.
        named: the member as the refusal names it, a pattern.
        converter_mock: reads the mock, edited.
    """
    model = converter_mock(("extra: [2] F64", extra))
    with pytest.raises(ValueError, match=rf"Bus\.A\.{named}, which the bus pin"):
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
