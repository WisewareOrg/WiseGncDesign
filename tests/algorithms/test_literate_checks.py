"""Runs every `check_*` of every literate algorithm module and holds the pairing of literate
modules to notebooks, by the rule in `tests/literate_documents.py` that CI's literate job also
uses: every module under `algorithms/gnc_algorithms/`, subpackages included, is an algorithm
module with a notebook and at least one `check_*`, except the `interfaces/` type modules, which
have neither; there is at least one; and every notebook belongs to an algorithm module or to a
notebook document. Notebook documents are never imported or run here."""

import importlib
import importlib.util
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_spec = importlib.util.spec_from_file_location(
    "literate_documents", Path(__file__).resolve().parents[1] / "literate_documents.py"
)
literate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(literate)


def _module(path: str) -> ModuleType:
    return importlib.import_module("gnc_algorithms." + path.replace("/", "."))


def _checks(module: ModuleType) -> list[tuple[str, Callable[[], None]]]:
    return [
        (name, function)
        for name, function in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("check_") and function.__module__ == module.__name__
    ]


WITH_CHECKS = sorted(path for path in literate.module_paths() if _checks(_module(path)))
CHECKS = [(path, name, check) for path in WITH_CHECKS for name, check in _checks(_module(path))]


def test_every_algorithm_module_is_literate_and_every_notebook_is_owned():
    algorithms = literate.algorithm_modules()
    owned = [f"{p}.ipynb" for p in algorithms]
    owned += [p.with_suffix(".ipynb").name for p in literate.notebook_documents()]

    assert algorithms, f"no algorithm module under {literate.SOURCES}"
    assert literate.literate_modules() == algorithms, "modules with a notebook"
    assert algorithms == WITH_CHECKS, "modules defining a check_*"
    assert sorted(
        "/".join(p.relative_to(literate.NOTEBOOKS).parts) for p in literate.notebooks()
    ) == sorted(owned)


@pytest.mark.parametrize("check", [c for _, _, c in CHECKS], ids=[f"{p}.{n}" for p, n, _ in CHECKS])
def test_check(check):
    check()


def _figure_modules() -> list[str]:
    return [path for path in WITH_CHECKS if hasattr(_module(path), "save_figures")]


@pytest.mark.parametrize("path", _figure_modules())
def test_figures_render(path, tmp_path):
    paths = _module(path).save_figures(tmp_path)

    assert paths and all(p.is_file() and p.stat().st_size > 0 for p in paths)


def _notebook(path: Path, outputs: list, execution_count: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cell = {"cell_type": "code", "source": [], "metadata": {}}
    cell.update(outputs=outputs, execution_count=execution_count)
    path.write_text(json.dumps({"cells": [cell], "metadata": {}, "nbformat": 4}))


def test_the_outputs_check_lists_every_notebook_carrying_output(monkeypatch, tmp_path):
    monkeypatch.setattr(literate, "NOTEBOOKS", tmp_path)
    _notebook(tmp_path / "clean.ipynb", [], None)
    _notebook(tmp_path / "sub" / "output.ipynb", [{"output_type": "stream", "text": ["x"]}], None)
    _notebook(tmp_path / "counted.ipynb", [], 3)
    _notebook(tmp_path / ".ipynb_checkpoints" / "kept-checkpoint.ipynb", [], 7)

    found = sorted(p.relative_to(tmp_path).as_posix() for p in literate.notebooks_with_outputs())

    assert found == ["counted.ipynb", "sub/output.ipynb"]


def test_the_literate_sets_reach_a_subpackage_module_with_a_notebook(monkeypatch, tmp_path, capsys):
    sources, notebooks = tmp_path / "gnc_algorithms", tmp_path / "notebooks"
    monkeypatch.setattr(literate, "SOURCES", sources)
    monkeypatch.setattr(literate, "NOTEBOOKS", notebooks)
    for module in ["__init__", "top", "pkg/__init__", "pkg/sub", "pkg/plain"]:
        (sources / f"{module}.py").parent.mkdir(parents=True, exist_ok=True)
        (sources / f"{module}.py").touch()
    _notebook(notebooks / "pkg" / "sub.ipynb", [], None)

    (sources / "interfaces").mkdir()
    (sources / "interfaces" / "sample.py").touch()

    assert literate.module_paths() == ["interfaces/sample", "pkg/plain", "pkg/sub", "top"]
    assert literate.algorithm_modules() == ["pkg/plain", "pkg/sub", "top"]
    assert literate.literate_modules() == ["pkg/sub"]
    assert literate.main(["modules"]) == 0
    assert literate.main(["sources"]) == 0
    assert capsys.readouterr().out.split() == [
        "gnc_algorithms.pkg.sub",
        "algorithms/gnc_algorithms/pkg/sub.py",
    ]
