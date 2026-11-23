"""FPP's types as named tuples, generated from the contract at import, and converters between them.

Importing the module reads the contract, `fsw.codegen.deployment.contract_files()`, once through
`fsw.codegen.fpp_model.read`, and binds each top-level FPP module as a namespace, so
`Gnc.ImuReading` is FPP's `Gnc.ImuReading`. `load(contract)` generates another contract's
tuples, such as a test's mock's, for `named` and the converters, leaving these namespaces as they
are. Each struct is a named tuple with no defaults. An array
is a numpy array, one of nested shape for an array of arrays, and has no tuple of its own; a scalar
is a number, and an enum value is its constant's name. A tuple converts nothing on construction.

Each component an algorithm's `.fpp` defines has three tuples in its FPP module, named for it:

- `<Name>Outputs`, a field per general output port, holding the port's one argument;
- `<Name>Telemetry`, a field per channel;
- `<Name>Parameters`, a field per parameter.

An output or telemetry field defaults to `None`, not written, which no FPP value is. A parameter
has a default only when its FPP declaration gives one, so the required parameters come first, each
group in FPP's order. A parameters tuple's `component` is its component's qualified name, and
`parameters_from` builds one from plain values. Why named tuples is in ADR 0004 rev 3.
"""

import functools
import operator
from collections import namedtuple
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from fsw.codegen.deployment import CONTRACT, Contract, contract_files
from fsw.codegen.fields import Form, form, plan
from fsw.codegen.fpp_model import Component, Member, Model, Struct, Types, read

__all__ = ["converter", "fields", "load", "named", "parameters_from"]

_STRUCTS: dict[type, tuple[Struct, Types]] = {}
"""Each struct's tuple, to its struct and the model's types, for `converter`."""

_COMPONENTS: dict[str, tuple[Component, Types]] = {}
"""Each algorithm's component, by its qualified name, with the model's types, for
`parameters_from`."""

_DEFINITIONS: dict[str, Struct | Component] = {}
"""Each struct and algorithm component tuples were generated for, by its qualified name."""

_LOADED: set[Contract] = set()
"""Each contract `load` has generated the tuples of."""


@functools.cache
def converter(source: type[Any], target: type[Any], *, copy: bool = True) -> Callable[[Any], Any]:
    """A function converting one struct's tuple to another's, each field matched by name.

    Fields are matched by `fields`, once per argument set, and the source is then read by position,
    so the value must be of `source` itself. An array field becomes a fresh array of the FPP type,
    or, with `copy` false, is the source's array itself; a scalar or an enum name passes as it is.

    Args:
        source: a struct's tuple.
        target: a struct's tuple.
        copy: false to pass the source's arrays through uncopied.

    Returns:
        The converter.

    Raises:
        ValueError: `source` or `target` is not a struct's tuple, or a field breaks the rule, naming
            it.
    """
    for given in (source, target):
        if given not in _STRUCTS:
            raise ValueError(f"{given.__name__} is not a struct's tuple")
    return _struct_converter(source, target, copy=copy)


@functools.cache
def fields(source: type[Any], target: type[Any]) -> tuple[tuple[Member, str, Form], ...]:
    """Each field of a struct's tuple `target`, with the `source` field it is taken from.

    Fields are matched by `fsw.codegen.fields.plan`'s rule: by name, ignoring case, of one shape and
    element type. A Basilisk payload's fields are read from its class's `__dtype__`.

    Args:
        source: a struct's tuple, or a Basilisk message payload's type.
        target: a struct's tuple.

    Returns:
        Each target member, the name of its source field and its form, in `target`'s order.

    Raises:
        ValueError: `target` is not a struct's tuple, or a field breaks the rule, naming it.
    """
    if target not in _STRUCTS:
        raise ValueError(f"{target.__name__} is not a struct's tuple")
    struct, types = _STRUCTS[target]
    return tuple(plan(struct, types, _source_forms(source), source.__name__))


def _struct_converter(source: type[Any], target: type[Any], *, copy: bool) -> Callable[[Any], Any]:
    """A converter between structs' tuples, reading the source by position.

    Args:
        source: a struct's tuple.
        target: a struct's tuple.
        copy: false to pass the source's arrays through uncopied.

    Returns:
        The converter.
    """
    planned = fields(source, target)
    indices = [source._fields.index(name) for _, name, _ in planned]
    pick = operator.itemgetter(*indices) if len(indices) > 1 else lambda value: (value[indices[0]],)
    steps = [functools.partial(np.array, dtype=element) if shape else _same for _, _, (shape, element) in planned]

    def convert(value: Any) -> Any:
        """The `target` tuple of a `source` tuple.

        Args:
            value: the `source` tuple.

        Returns:
            The tuple.

        Raises:
            TypeError: `value` is not of `source`, naming both.
        """
        if type(value) is not source:
            raise TypeError(f"the value is a {type(value).__name__}, not the struct's tuple {_STRUCTS[source][0].name}")
        if not copy:
            return target._make(pick(value))
        return target._make([to(field) for to, field in zip(steps, pick(value), strict=True)])

    return convert


def named(name: str) -> type[Any]:
    """A struct's or a component's tuple, by its FPP qualified name.

    Args:
        name: such as `Gnc.ImuReading` or `Gnc.ImuDeadReckonerParameters`.

    Returns:
        The tuple.
    """
    *modules, base = name.split(".")
    space = _namespaces[modules[0]]
    for module in modules[1:]:
        space = getattr(space, module)
    return getattr(space, base)


def parameters_from(tuple_type: type[Any], values: Mapping[str, Any]) -> Any:
    """A component's parameters tuple from plain values, such as a JSON object's.

    An array field becomes a fresh array of its FPP shape and type; a scalar or an enum name passes
    as it is. A field missing from `values`, or one the tuple lacks, raises as the tuple does.

    Args:
        tuple_type: a component's `<Name>Parameters` tuple.
        values: each parameter's value by name.

    Returns:
        The tuple.

    Raises:
        ValueError: an array field's value is not of its FPP shape, naming the field.
    """
    component, types = _COMPONENTS[tuple_type.component]
    converted = dict(values)
    for parameter in component.parameters:
        shape, element = form(Member(parameter.name, parameter.type, None), types)
        if shape and parameter.name in converted:
            value = np.array(converted[parameter.name], dtype=element)
            if value.shape != shape:
                raise ValueError(f"{component.name}.{parameter.name} is {shape}, but its value is {value.shape}")
            converted[parameter.name] = value
    return tuple_type(**converted)


def _same(value: Any) -> Any:
    """A scalar or an enum name, which a converter passes as it is.

    Args:
        value: the field's value.

    Returns:
        The value, unchanged.
    """
    return value


def _source_forms(source: type[Any]) -> dict[str, tuple[str, Form]]:
    """Each field of a converter's source, by its name in lower case.

    Args:
        source: a struct's tuple, or a Basilisk message payload's type.

    Returns:
        Each field's name and form.
    """
    if source in _STRUCTS:
        struct, types = _STRUCTS[source]
        return {m.name.lower(): (m.name, form(m, types)) for m in struct.members}
    fields = source.__dtype__.fields
    return {name.lower(): (name, (fields[name][0].shape, fields[name][0].base)) for name in source.__dtype__.names}


def _build(model: Model, algorithms: Collection[Path], kept: Collection[str] = ()) -> dict[str, SimpleNamespace]:
    """The tuples of a model's structs and of its algorithms' components, by top-level FPP module.

    Each struct's tuple is recorded for `converter`, and each algorithm's component for
    `parameters_from`.

    Args:
        model: the model.
        algorithms: the algorithms' `.fpp` files; a component one of them defines gets tuples.
        kept: qualified names already generated with an equal definition, whose tuples are kept
            and not rebuilt.

    Returns:
        Each top-level module's namespace, nested modules as namespaces within it.
    """
    namespaces: dict[str, SimpleNamespace] = {}

    def place(qualified: str, cls: type) -> None:
        """Puts a tuple in its module's namespace, its `__qualname__` the FPP qualified name.

        `fsw.python.rio.messages` reads the qualified name to find a bus struct's payload.

        Args:
            qualified: its FPP qualified name, such as `Gnc.ImuReading`.
            cls: the tuple.
        """
        *modules, name = qualified.split(".")
        cls.__qualname__ = qualified
        space = namespaces.setdefault(modules[0], SimpleNamespace())
        for module in modules[1:]:
            space = space.__dict__.setdefault(module, SimpleNamespace())
        setattr(space, name, cls)

    for name, struct in model.types.items():
        if isinstance(struct, Struct) and name not in kept:
            cls = namedtuple(name.rsplit(".", 1)[-1], [m.name for m in struct.members])
            _STRUCTS[cls] = struct, model.types
            _DEFINITIONS[name] = struct
            place(name, cls)

    files = {Path(f).resolve() for f in algorithms}
    for component in model.components.values():
        if component.file.resolve() in files and component.name not in kept:
            _COMPONENTS[component.name] = component, model.types
            _DEFINITIONS[component.name] = component
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
                f"{component.name}.{port.name}: an output port is a field only with one argument and no port array"
            )
    name = component.name.rsplit(".", 1)[-1]
    outputs = [p.name for p in component.outputs]
    channels = [c.name for c in component.channels]
    required = [p.name for p in component.parameters if p.default is None]
    defaulted = [p for p in component.parameters if p.default is not None]
    parameters = namedtuple(
        f"{name}Parameters",
        [*required, *(p.name for p in defaulted)],
        defaults=[p.default for p in defaulted],
    )
    parameters.component = component.name
    return {
        "Outputs": namedtuple(f"{name}Outputs", outputs, defaults=[None] * len(outputs)),
        "Telemetry": namedtuple(f"{name}Telemetry", channels, defaults=[None] * len(channels)),
        "Parameters": parameters,
    }


def load(contract: Contract) -> None:
    """Generates a contract's tuples, once per contract, so `named` and the converters resolve them.

    A struct or algorithm component already generated with an equal definition, such as the
    framework's and the interfaces' every contract shares, keeps its tuples. A module the
    repository's contract already has is merged into a copy that `named` reads, so this module's
    namespaces, the repository's, gain nothing of another contract's.

    Args:
        contract: the contract.

    Raises:
        ValueError: a struct or algorithm component is already generated from another definition,
            naming it.
    """
    if contract in _LOADED:
        return
    model = read(contract_files(contract=contract))
    files = {Path(f).resolve() for f in contract.algorithms}
    definitions: dict[str, Struct | Component] = {name: t for name, t in model.types.items() if isinstance(t, Struct)}
    definitions |= {c.name: c for c in model.components.values() if c.file.resolve() in files}
    for name, definition in definitions.items():
        if _DEFINITIONS.get(name, definition) != definition:
            raise ValueError(f"{name} is already generated from another definition")
    for top, space in _build(model, contract.algorithms, frozenset(_DEFINITIONS)).items():
        held = _namespaces.get(top)
        _namespaces[top] = space if held is None else _merged(held, space)
    _LOADED.add(contract)


def _merged(held: SimpleNamespace, space: SimpleNamespace) -> SimpleNamespace:
    """A copy of a namespace with another's names it lacks, nested namespaces merged alike.

    Args:
        held: the namespace copied; a name it has keeps its value, and it is left as it is.
        space: the namespace whose names are added.

    Returns:
        The copy.
    """
    merged = SimpleNamespace(**vars(held))
    for name, value in vars(space).items():
        kept = getattr(held, name, None)
        if isinstance(value, SimpleNamespace) and isinstance(kept, SimpleNamespace):
            setattr(merged, name, _merged(kept, value))
        elif kept is None:
            setattr(merged, name, value)
    return merged


_namespaces: dict[str, SimpleNamespace] = {}
load(CONTRACT)
globals().update(_namespaces)
__all__ += sorted(_namespaces)
