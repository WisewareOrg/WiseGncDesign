"""The stub `fpp_types_stub` emits for `fpp_types` declares what the runtime module holds.

Needs the F´ framework clone `just _sync` fetches, not an F´ build.
"""

import ast
from types import SimpleNamespace
from typing import Any

import pytest

from fsw.codegen import fpp_types, fpp_types_stub


def _classes(body: list[ast.stmt]) -> dict[str, ast.ClassDef]:
    """The classes defined directly in a body.

    Args:
        body: a module's or class's statements.

    Returns:
        Each class by name.
    """
    return {node.name: node for node in body if isinstance(node, ast.ClassDef)}


def _runtime(space: SimpleNamespace, path: str = "") -> dict[str, type[Any]]:
    """Every tuple class in a namespace, by dotted path, walking nested namespaces.

    Args:
        space: a namespace the runtime module exposes.
        path: the dotted path of `space`, empty at the top.

    Returns:
        The tuple classes by path, such as `Svc.Ccsds.TCHeader`.
    """
    found: dict[str, type[Any]] = {}
    for name, value in vars(space).items():
        if isinstance(value, SimpleNamespace):
            found |= _runtime(value, f"{path}{name}.")
        else:
            found[f"{path}{name}"] = value
    return found


def _tree() -> dict[str, type[Any]]:
    """Every tuple class the runtime module exposes, by dotted path.

    Returns:
        The tuple classes by path, walking each namespace in `fpp_types.__all__`.
    """
    found: dict[str, type[Any]] = {}
    for name in fpp_types.__all__:
        value = getattr(fpp_types, name)
        if isinstance(value, SimpleNamespace):
            found |= _runtime(value, f"{name}.")
    return found


def _stub_class(stub: ast.Module, path: str) -> ast.ClassDef | None:
    """A class in the stub by dotted path.

    Args:
        stub: the parsed stub.
        path: the dotted path, such as `Svc.Ccsds.TCHeader`.

    Returns:
        The class, or None when some part of the path is not defined.
    """
    node = None
    body = stub.body
    for part in path.split("."):
        node = _classes(body).get(part)
        if node is None:
            return None
        body = node.body
    return node


def _annotations(node: ast.ClassDef) -> list[ast.AnnAssign]:
    """A class's annotated names, `ClassVar`s apart.

    Args:
        node: a stub class.

    Returns:
        Its annotated assignments to a name that are not `ClassVar`.
    """
    return [
        statement
        for statement in node.body
        if isinstance(statement, ast.AnnAssign) and "ClassVar" not in ast.unparse(statement.annotation)
    ]


@pytest.fixture(scope="module")
def source() -> str:
    """The stub text, rendered once.

    Returns:
        What `fpp_types_stub.render` emits for the contract.
    """
    return fpp_types_stub.render()


@pytest.fixture(scope="module")
def stub(source: str) -> ast.Module:
    """The stub parsed, once.

    Args:
        source: the stub text.

    Returns:
        Its syntax tree.
    """
    return ast.parse(source)


@pytest.fixture(scope="module")
def tree() -> dict[str, type[Any]]:
    """The runtime's tuple classes by dotted path, walked once; never empty.

    Returns:
        The tuple classes by path.
    """
    found = _tree()
    assert found, "the runtime module exposes no tuple class, so every stub check would pass vacuously"
    return found


@pytest.fixture(scope="module")
def namespaces() -> list[str]:
    """The runtime module's top-level namespaces.

    Returns:
        Each name in `fpp_types.__all__` that is a `SimpleNamespace`.
    """
    names = [name for name in fpp_types.__all__ if isinstance(getattr(fpp_types, name), SimpleNamespace)]
    assert names, "the runtime module exposes no namespace, so every stub check would pass vacuously"
    return names


def _field_nodes(node: ast.ClassDef) -> list[ast.AnnAssign]:
    """A class's annotated names that are plain names, `ClassVar`s apart.

    Args:
        node: a stub class.

    Returns:
        Its annotated assignments to a name that are not `ClassVar`.
    """
    return [a for a in _annotations(node) if isinstance(a.target, ast.Name)]


def _top_level_names(stub: ast.Module) -> set[str]:
    """The names the stub defines at its top level.

    Args:
        stub: the parsed stub.

    Returns:
        Each function, class and assigned name.
    """
    defined: set[str] = set()
    for node in stub.body:
        if isinstance(node, ast.FunctionDef | ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.Assign):
            defined |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return defined


def test_the_stub_defines_every_name_the_runtime_module_exports(stub: ast.Module):
    """Each name in `fpp_types.__all__` is defined at the stub's top level.

    Args:
        stub: the parsed stub.
    """
    missing = set(fpp_types.__all__) - _top_level_names(stub)

    assert missing == set(), f"the stub does not define {sorted(missing)}, which the runtime module exports"


def test_the_stub_says_which_emitter_generated_it(source: str):
    """The stub's first line is its generated-by header.

    Args:
        source: the stub text.
    """
    assert source.splitlines()[0] == "# Generated by fsw.codegen.fpp_types_stub; never committed."


def test_the_stub_repeats_the_runtime_module_s_all(stub: ast.Module):
    """The stub's `__all__` is the runtime module's.

    Args:
        stub: the parsed stub.
    """
    alls = [
        ast.literal_eval(n.value)
        for n in stub.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
    ]

    assert alls == [fpp_types.__all__], "the stub must hold exactly one `__all__`, equal to the runtime module's"


def test_the_stub_declares_every_tuple_at_the_runtime_s_nested_path(stub: ast.Module, tree: dict[str, type[Any]]):
    """Each tuple class the runtime walks appears as the same nested class path.

    Args:
        stub: the parsed stub.
        tree: the runtime's tuple classes by path.
    """
    missing = [path for path in tree if _stub_class(stub, path) is None]

    assert missing == [], f"the stub declares no class at {missing}, which the runtime module holds"


def test_each_tuple_class_declares_the_runtime_s_fields_in_the_runtime_s_order(
    stub: ast.Module, tree: dict[str, type[Any]]
):
    """A tuple class's annotated fields, in order, equal the runtime class's `_fields`.

    Args:
        stub: the parsed stub.
        tree: the runtime's tuple classes by path.
    """
    mismatched = {}
    for path, cls in tree.items():
        node = _stub_class(stub, path)
        declared = [a.target.id for a in _field_nodes(node) if isinstance(a.target, ast.Name)] if node else None
        if declared != list(cls._fields):
            mismatched[path] = (declared, list(cls._fields))

    assert mismatched == {}, f"stub fields differ from the runtime's, as path: (stub, runtime): {mismatched}"


def test_a_field_has_a_default_exactly_when_the_runtime_class_has_one(stub: ast.Module, tree: dict[str, type[Any]]):
    """A stub field carries a default when it is in the runtime class's `_field_defaults`, and not otherwise.

    Args:
        stub: the parsed stub.
        tree: the runtime's tuple classes by path.
    """
    mismatched = {}
    for path, cls in tree.items():
        node = _stub_class(stub, path)
        defaulted = (
            {a.target.id for a in _field_nodes(node) if isinstance(a.target, ast.Name) and a.value is not None}
            if node
            else None
        )
        if defaulted != set(cls._field_defaults):
            mismatched[path] = (defaulted, set(cls._field_defaults))

    assert mismatched == {}, f"stub defaults differ from the runtime's, as path: (stub, runtime): {mismatched}"


def test_a_tuple_class_is_a_named_tuple(stub: ast.Module, tree: dict[str, type[Any]]):
    """A runtime tuple class derives only from `NamedTuple` in the stub.

    Args:
        stub: the parsed stub.
        tree: the runtime's tuple classes by path.
    """
    wrong = {}
    for path in tree:
        node = _stub_class(stub, path)
        bases = [ast.unparse(base) for base in node.bases] if node else None
        if bases != ["NamedTuple"]:
            wrong[path] = bases

    assert wrong == {}, f"these stub classes do not derive only from NamedTuple, as path: bases: {wrong}"


def test_a_namespace_is_a_plain_class(stub: ast.Module, namespaces: list[str]):
    """A runtime top-level namespace is a class with no bases in the stub.

    Args:
        stub: the parsed stub.
        namespaces: the runtime's top-level namespaces.
    """
    classes = _classes(stub.body)
    wrong = {name: [ast.unparse(b) for b in classes[name].bases] if name in classes else None for name in namespaces}
    wrong = {name: bases for name, bases in wrong.items() if bases != []}

    assert wrong == {}, f"these namespaces are not plain classes in the stub, as name: bases: {wrong}"


def test_a_parameters_tuple_declares_its_component_as_a_class_variable(stub: ast.Module, tree: dict[str, type[Any]]):
    """A runtime tuple with a `component` attribute declares it `ClassVar[str]` in the stub, and no other does.

    Args:
        stub: the parsed stub.
        tree: the runtime's tuple classes by path.
    """
    wrong = {}
    for path, cls in tree.items():
        node = _stub_class(stub, path)
        declared = (
            [
                ast.unparse(s.annotation)
                for s in node.body
                if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name) and s.target.id == "component"
            ]
            if node
            else None
        )
        expected = ["ClassVar[str]"] if hasattr(cls, "component") and "component" not in cls._fields else []
        if declared != expected:
            wrong[path] = (declared, expected)

    assert wrong == {}, f"`component` is declared wrongly, as path: (stub, expected): {wrong}"
    assert any(hasattr(cls, "component") for cls in tree.values()), "no runtime tuple has a component to check"


ANNOTATIONS = [
    ("Gnc.ImuReading", "angVelPlatform", "np.ndarray"),
    ("Gnc.ImuDeadReckonerParameters", "mu", "float"),
    ("Svc.Ccsds.SaMapEntry", "portIndex", "int"),
    ("ComCfg.FrameContext", "hasSecHdr", "bool"),
    ("Fw.TimeValue", "timeBase", "str"),
    ("Gnc.WheelSpinnerOutputs", "wheelOut", "Gnc.WheelCommand | None"),
    ("Gnc.WheelSpinnerTelemetry", "wheelTorque", "float | None"),
    ("Gnc.ImuDeadReckonerTelemetry", "navState", "str | None"),
    ("Gnc.ImuDeadReckonerTelemetry", "bodyEciPos", "np.ndarray | None"),
    ("Gnc.WheelSpinnerParameters", "motorTorque", "float"),
    ("Gnc.WheelCommand", "motorTorque", "np.ndarray"),
]
"""A real field per mapping row and wrapping rule; the contract has no plain `string` field to add."""


@pytest.mark.parametrize(("path", "field", "expected"), ANNOTATIONS)
def test_a_field_is_annotated_as_its_fpp_type_maps(stub: ast.Module, path: str, field: str, expected: str):
    """A representative field per type mapping is annotated with the literal annotation the mapping gives.

    Args:
        stub: the parsed stub.
        path: the dotted path of the tuple class.
        field: the field's name.
        expected: the annotation the mapping gives it.
    """
    node = _stub_class(stub, path)
    assert node is not None, f"the stub declares no class {path}; the contract no longer holds this field"
    declared = {a.target.id: ast.unparse(a.annotation) for a in _field_nodes(node) if isinstance(a.target, ast.Name)}
    assert field in declared, f"{path} declares no field {field}; the contract no longer holds it"

    assert declared[field] == expected, f"{path}.{field} is annotated {declared[field]}, expected {expected}"
