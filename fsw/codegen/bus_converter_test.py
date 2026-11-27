"""The F´ CDH generator: the C++ it emits for `Cdh.BusConverter`'s roles, and what it refuses.

Each test reads a mock model of two roles, so none needs the F´ framework clone.
"""

from collections.abc import Callable

import pytest

from fsw.codegen.bus_converter import render
from fsw.codegen.fpp_model import Model


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
    files = render(
        converter_mock(
            (
                "    sync input port bIn",
                "    sync input port cIn: Bus.A\n    output port cOut: Gnc.AIcd\n    sync input port bIn",
            ),
        )
    )
    pins = files["BusConverterPins.hpp"]
    functions = files["BusConverterPins.cpp"]
    assert pins.count('"bus_A"') == 1
    assert pins.count('"bus_B"') == 1
    for role, bus in (("a", "Bus::A"), ("c", "Bus::A"), ("b", "Bus::B")):
        assert f'"cdh_{role}"' in pins
        assert f"{bus} msg;" in functions
        assert f"Cdh::BusConverter::convert_{role}(msg)" in functions


@pytest.mark.parametrize(
    ("edits", "match"),
    [
        pytest.param(
            (
                ("struct B { n: [2] F64 }", "struct B { m: [2] Gnc.Row }"),
                ("struct BIcd { n: [2] F64 }", "struct BIcd { m: Mat }"),
            ),
            r"Gnc\.BIcd\.m is \(2, 3\) float64, which the F´ CDH",
            id="array-of-arrays",
        ),
        pytest.param(
            (
                ("struct A { extra", "struct A { f: [2] bool, extra"),
                ("struct AIcd { V", "struct AIcd { f: [2] bool, V"),
            ),
            r"Gnc\.AIcd\.f is \(2,\) bool, which the F´ CDH",
            id="bool",
        ),
        pytest.param(
            (
                ("struct A { extra", "struct A { e: [2] Gnc.Mode, extra"),
                ("struct AIcd { V", "struct AIcd { e: [2] Mode, V"),
            ),
            r"Gnc\.AIcd\.e is \(2,\) Gnc\.Mode, which the F´ CDH",
            id="not-a-number",
        ),
        pytest.param(
            (("extra: [2] F64", "extra: F64"),),
            r"Bus\.A\.extra is F64, which the bus pin",
            id="bus-scalar",
        ),
        pytest.param(
            (("extra: [2] F64", "extra: [2] U32"),),
            r"Bus\.A\.extra is \[2\] U32, which the bus pin",
            id="bus-unused-primitive",
        ),
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
