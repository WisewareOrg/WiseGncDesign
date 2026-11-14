"""FPP's types as named tuples, generated from the contract at import, and converters between them.

Importing the module reads the contract, `fsw.codegen.deployment.contract_files()`, once through
`fsw.codegen.fpp_model.read`, and binds each top-level FPP module as a namespace, so
`Gnc.ImuReading` is FPP's `Gnc.ImuReading`. Each struct is a named tuple with no defaults. An array
is a numpy array, one of nested shape for an array of arrays, and has no tuple of its own; a scalar
is a number, and an enum value is its constant's name. A tuple converts nothing on construction.

Each component an algorithm's `.fpp` defines has three tuples in its FPP module, named for it:

- `<Name>Outputs`, a field per general output port, holding the port's one argument;
- `<Name>Telemetry`, a field per channel;
- `<Name>Parameters`, a field per parameter.

An output or telemetry field defaults to `None`, not written, which no FPP value is. A parameter
has a default only when its FPP declaration gives one, so the required parameters come first, each
group in FPP's order. Why named tuples is in ADR 0004 rev 2.
"""

import functools
from collections import namedtuple
from collections.abc import Callable, Collection
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from fsw.codegen.deployment import algorithm_files, contract_files
from fsw.codegen.fpp_model import Array, Component, Enum, Model, Struct, read

__all__ = ["converter"]

_DTYPES = {
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

_STRUCTS: dict[type, tuple[Struct, dict[str, Struct | Enum | Array]]] = {}
"""Each struct's tuple, to its struct and the model's types, for `converter`."""


def converter(source: type, target: type) -> Callable[[Any], Any]:
    """A function converting a `source` value to a `target` tuple, each field taken by name.

    Every field of `target` is taken from the `source` field of its name, ignoring case; fields of
    `source` that `target` lacks are dropped. An array field becomes a fresh array of the FPP type;
    a scalar or an enum name passes as it is.

    Args:
        source: a struct's tuple, or a Basilisk message payload's type.
        target: a struct's tuple.

    Returns:
        The converter.

    Raises:
        ValueError: a field of `target` is missing from `source`, or is a struct, naming it.
    """
    struct, types = _STRUCTS[target]
    names = source._fields if hasattr(source, "_fields") else source.__dtype__.names
    by_name = {name.lower(): name for name in names}
    plan = []
    for member in struct.members:
        if member.name.lower() not in by_name:
            raise ValueError(f"{source.__name__} has no field {member.name} for {struct.name}")
        member_type = types.get(member.type)
        if isinstance(member_type, Struct):
            raise ValueError(f"{struct.name}.{member.name} is a struct, which is not converted")
        if member.size is not None or isinstance(member_type, Array):
            convert = functools.partial(np.array, dtype=_dtype(member.type, types))
        else:
            convert = _same
        plan.append((by_name[member.name.lower()], convert))

    def convert_value(value: Any) -> Any:
        """The `target` tuple of a `source` value.

        Args:
            value: the `source` value.

        Returns:
            The tuple.
        """
        return target._make([change(getattr(value, field)) for field, change in plan])

    return convert_value


def _same(value: Any) -> Any:
    """A scalar or an enum name, which a converter passes as it is.

    Args:
        value: the field's value.

    Returns:
        The value, unchanged.
    """
    return value


def _dtype(type_name: str, types: dict[str, Struct | Enum | Array]) -> np.dtype:
    """The numpy type of a type's numeric elements, through any arrays of arrays.

    Args:
        type_name: a primitive's or an array type's name.
        types: the model's types.

    Returns:
        The element's native-endian numpy type.
    """
    while isinstance(types.get(type_name), Array):
        type_name = types[type_name].element
    return _DTYPES[type_name]


def _build(model: Model, algorithms: Collection[Path]) -> dict[str, SimpleNamespace]:
    """The tuples of a model's structs and of its algorithms' components, by top-level FPP module.

    Args:
        model: the model.
        algorithms: the algorithms' `.fpp` files; a component one of them defines gets tuples.

    Returns:
        Each top-level module's namespace, nested modules as namespaces within it.
    """
    namespaces: dict[str, SimpleNamespace] = {}

    def place(qualified: str, cls: type) -> None:
        """Puts a tuple in its module's namespace, named as FPP names it.

        Args:
            qualified: its FPP qualified name, such as `Gnc.ImuReading`.
            cls: the tuple.
        """
        *modules, name = qualified.split(".")
        cls.__module__ = __name__
        cls.__qualname__ = qualified
        space = namespaces.setdefault(modules[0], SimpleNamespace())
        for module in modules[1:]:
            space = space.__dict__.setdefault(module, SimpleNamespace())
        setattr(space, name, cls)

    for name, struct in model.types.items():
        if isinstance(struct, Struct):
            cls = namedtuple(name.rsplit(".", 1)[-1], [m.name for m in struct.members])
            _STRUCTS[cls] = struct, model.types
            place(name, cls)

    files = {Path(f).resolve() for f in algorithms}
    for component in model.components.values():
        if component.file.resolve() in files:
            for suffix, cls in _component_tuples(component).items():
                place(component.name + suffix, cls)
    return namespaces


def _component_tuples(component: Component) -> dict[str, type]:
    """An algorithm's component's outputs, telemetry and parameters tuples.

    Args:
        component: the component.

    Returns:
        Each tuple, by its name's suffix.

    Raises:
        ValueError: an output port is an array or has other than one argument, naming it.
    """
    for port in component.outputs:
        if port.size != 1 or len(port.args) != 1:
            raise ValueError(
                f"{component.name}.{port.name}: an output port is a field only with one argument"
                " and no port array"
            )
    name = component.name.rsplit(".", 1)[-1]
    outputs = [p.name for p in component.outputs]
    channels = [c.name for c in component.channels]
    required = [p.name for p in component.parameters if p.default is None]
    defaulted = [p for p in component.parameters if p.default is not None]
    return {
        "Outputs": namedtuple(f"{name}Outputs", outputs, defaults=[None] * len(outputs)),
        "Telemetry": namedtuple(f"{name}Telemetry", channels, defaults=[None] * len(channels)),
        "Parameters": namedtuple(
            f"{name}Parameters",
            [*required, *(p.name for p in defaulted)],
            defaults=[p.default for p in defaulted],
        ),
    }


_namespaces = _build(read(contract_files()), algorithm_files())
globals().update(_namespaces)
__all__ += sorted(_namespaces)
