"""How a struct's fields are taken from a source's: the one rule both builds' CDH converters follow.

Every field of the target struct is taken from the source field of its name, ignoring case, which
must have its shape and element type; source fields the target lacks are dropped, and a target
field that is itself a struct is not converted. `fsw.codegen.fpp_types.converter` applies it to
Python values, and `fsw.codegen.bus_converter` to the F´ build's generated C++.
"""

from typing import Any

import numpy as np

from fsw.codegen.fpp_model import Array, Enum, Member, Struct

__all__ = ["DTYPES", "Form", "form", "plan"]

DTYPES = {
    "F32": np.dtype("float32"),
    "F64": np.dtype("float64"),
    "I8": np.dtype("int8"),
    "I16": np.dtype("int16"),
    "I32": np.dtype("int32"),
    "I64": np.dtype("int64"),
    "U8": np.dtype("uint8"),
    "U16": np.dtype("uint16"),
    "U32": np.dtype("uint32"),
    "U64": np.dtype("uint64"),
    "bool": np.dtype("bool"),
}
"""Each numeric FPP primitive as its native-endian numpy type."""

Form = tuple[tuple[int, ...], np.dtype | str]
"""A field's shape, and its element's numpy type, or the name of its element's FPP type when that
is not a number."""


def form(member: Member, types: dict[str, Struct | Enum | Array]) -> Form:
    """A struct member's shape and element type, through any arrays of arrays.

    Args:
        member: the member.
        types: the model's types.

    Returns:
        Its form.
    """
    shape = () if member.size is None else (member.size,)
    type_name = member.type
    while isinstance(array := types.get(type_name), Array):
        shape += (array.size,)
        type_name = array.element
    return shape, DTYPES.get(type_name, type_name)


def plan(
    target: Struct,
    types: dict[str, Any],
    sources: dict[str, tuple[str, Form]],
    source_name: str,
) -> list[tuple[Member, str, Form]]:
    """Each field of `target`, with the source field it is taken from.

    Args:
        target: the struct converted to.
        types: the model's types, `target`'s among them.
        sources: each source field's name and form, by its name in lower case.
        source_name: the source's name, for errors.

    Returns:
        Each target member, the name of its source field and its form, in `target`'s order.

    Raises:
        ValueError: a field of `target` is a struct, is missing from the source, or differs from
            it in shape or element type, naming it.
    """
    planned = []
    for member in target.members:
        if isinstance(types.get(member.type), Struct):
            raise ValueError(f"{target.name}.{member.name} is a struct, which is not converted")
        if member.name.lower() not in sources:
            raise ValueError(f"{source_name} has no field {member.name} for {target.name}")
        name, source_form = sources[member.name.lower()]
        shape, element = form(member, types)
        if source_form != (shape, element):
            raise ValueError(
                f"{target.name}.{member.name} is {shape} {element}, but {source_name}.{name}"
                f" is {source_form[0]} {source_form[1]}"
            )
        planned.append((member, name, (shape, element)))
    return planned
