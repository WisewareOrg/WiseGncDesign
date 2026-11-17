"""The field rule both builds' CDH converters follow, over hand-built mock structs.

Needs no FPP model: the structs, members and arrays are built directly, so a third consumer of
`plan` meets the same contract the two that exist do.
"""

import numpy as np
import pytest

from fsw.codegen.fields import form, plan
from fsw.codegen.fpp_model import Array, Member, Struct

TYPES = {
    "Mock.Row": Array("Mock.Row", 3, "F64"),
    "Mock.Mat": Array("Mock.Mat", 2, "Mock.Row"),
    "Mock.Inner": Struct("Mock.Inner", (Member("a", "F64", None),)),
}
"""The mock's types: an array, an array of arrays and a struct."""

TARGET = Struct("Mock.Target", (Member("Rate", "Mock.Row", None), Member("count", "U16", None)))
"""A target with a 3-vector by array type and a scalar."""


def _sources(*members: Member) -> dict:
    """Each source member's name and form, by its name in lower case, as `plan` takes them.

    Args:
        *members: the source's members.

    Returns:
        The sources.
    """
    return {m.name.lower(): (m.name, form(m, TYPES)) for m in members}


def test_each_target_field_comes_from_its_namesake_ignoring_case_and_extras_are_dropped() -> None:
    """`Rate` comes from `rate`, `count` from `COUNT`; the source's `extra` is not planned."""
    sources = _sources(
        Member("extra", "I32", None), Member("COUNT", "U16", None), Member("rate", "F64", 3)
    )
    planned = plan(TARGET, TYPES, sources, "Mock.Source")
    assert [(member.name, name, f) for member, name, f in planned] == [
        ("Rate", "rate", ((3,), np.dtype("float64"))),
        ("count", "COUNT", ((), np.dtype("uint16"))),
    ]


def test_a_field_missing_from_the_source_is_refused_by_name() -> None:
    """A source without `count` raises, naming the source, the field and the target."""
    with pytest.raises(ValueError, match="Mock.Source has no field count for Mock.Target"):
        plan(TARGET, TYPES, _sources(Member("rate", "F64", 3)), "Mock.Source")


def test_a_target_field_that_is_a_struct_is_refused_by_name() -> None:
    """A target member of struct type is not converted, naming it."""
    target = Struct("Mock.Target", (Member("inner", "Mock.Inner", None),))
    sources = _sources(Member("inner", "Mock.Inner", None))
    with pytest.raises(
        ValueError, match=r"Mock\.Target\.inner is a struct, which is not converted"
    ):
        plan(target, TYPES, sources, "Mock.Source")


def test_a_field_of_another_shape_is_refused_by_name() -> None:
    """A four-element `rate` cannot fill the three-element `Rate`, naming both."""
    sources = _sources(Member("rate", "F64", 4), Member("count", "U16", None))
    with pytest.raises(
        ValueError, match=r"Mock\.Target\.Rate is \(3,\) float64, but Mock\.Source\.rate is \(4,\)"
    ):
        plan(TARGET, TYPES, sources, "Mock.Source")


def test_a_field_of_another_element_type_is_refused_by_name() -> None:
    """An `F32` `rate` cannot fill the `F64` `Rate`, naming both."""
    sources = _sources(Member("rate", "F32", 3), Member("count", "U16", None))
    with pytest.raises(
        ValueError,
        match=r"Mock\.Target\.Rate is \(3,\) float64, but Mock\.Source\.rate is \(3,\) float32",
    ):
        plan(TARGET, TYPES, sources, "Mock.Source")


def test_a_form_follows_arrays_of_arrays_and_names_a_type_that_is_not_a_number() -> None:
    """`[4] Mat` is four by two by three `F64`s; an enum or struct element keeps its FPP name."""
    assert form(Member("m", "Mock.Mat", 4), TYPES) == ((4, 2, 3), np.dtype("float64"))
    assert form(Member("i", "Mock.Inner", None), TYPES) == ((), "Mock.Inner")
