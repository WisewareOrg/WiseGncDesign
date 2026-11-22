"""The field rule both builds' CDH converters follow, over hand-built mock structs.

Needs no FPP model: the structs, members and arrays are built directly, so a third consumer of
`plan` meets the same contract the two that exist do.
"""

import numpy as np
import pytest

from fsw.codegen.fields import form, plan
from fsw.codegen.fpp_model import Array, Member, Struct, Types

TYPES: Types = {
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
    sources = _sources(Member("extra", "I32", None), Member("COUNT", "U16", None), Member("rate", "F64", 3))
    planned = plan(TARGET, TYPES, sources, "Mock.Source")
    assert [(member.name, name, f) for member, name, f in planned] == [
        ("Rate", "rate", ((3,), np.dtype("float64"))),
        ("count", "COUNT", ((), np.dtype("uint16"))),
    ]


@pytest.mark.parametrize(
    ("target", "sources", "match"),
    [
        pytest.param(
            TARGET,
            _sources(Member("rate", "F64", 3)),
            "Mock.Source has no field count for Mock.Target",
            id="missing",
        ),
        pytest.param(
            Struct("Mock.Target", (Member("inner", "Mock.Inner", None),)),
            _sources(Member("inner", "Mock.Inner", None)),
            r"Mock\.Target\.inner is a struct, which is not converted",
            id="struct",
        ),
        pytest.param(
            TARGET,
            _sources(Member("rate", "F64", 4), Member("count", "U16", None)),
            r"Mock\.Target\.Rate is \(3,\) float64, but Mock\.Source\.rate is \(4,\)",
            id="shape",
        ),
        pytest.param(
            TARGET,
            _sources(Member("rate", "F32", 3), Member("count", "U16", None)),
            r"Mock\.Target\.Rate is \(3,\) float64, but Mock\.Source\.rate is \(3,\) float32",
            id="element-type",
        ),
    ],
)
def test_a_field_the_rule_cannot_fill_is_refused_by_name(target: Struct, sources: dict, match: str) -> None:
    """A missing field, a struct field, another shape and another element type are each refused.

    Args:
        target: the target struct.
        sources: the source's members, as `plan` takes them.
        match: the refusal, naming the source, the field and the target.
    """
    with pytest.raises(ValueError, match=match):
        plan(target, TYPES, sources, "Mock.Source")
