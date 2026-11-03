"""Runs every `check_*` of every literate algorithm module and holds the pairing of literate
modules to notebooks, over every module under `algorithms/gnc_algorithms/`, subpackages
included: the modules with a notebook `notebooks/<path>.ipynb` are exactly the modules defining
a `check_*`, there is at least one, and every notebook belongs to such a module or to a notebook
document `notebooks/<name>.py`. Notebook documents are never imported or run here."""

import importlib
import inspect
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "algorithms" / "gnc_algorithms"
NOTEBOOKS = ROOT / "notebooks"


def _module_paths() -> list[str]:
    """Every module under `gnc_algorithms`, as its path below the package without `.py`."""
    return sorted(
        "/".join(p.relative_to(SOURCES).with_suffix("").parts)
        for p in SOURCES.rglob("*.py")
        if p.name != "__init__.py"
    )


def _module(path: str) -> ModuleType:
    return importlib.import_module("gnc_algorithms." + path.replace("/", "."))


def _checks(module: ModuleType) -> list[tuple[str, Callable[[], None]]]:
    return [
        (name, function)
        for name, function in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("check_") and function.__module__ == module.__name__
    ]


MODULES = _module_paths()
WITH_CHECKS = sorted(path for path in MODULES if _checks(_module(path)))
CHECKS = [(path, name, check) for path in WITH_CHECKS for name, check in _checks(_module(path))]


def test_literate_modules_are_exactly_the_modules_with_checks_and_every_notebook_is_owned():
    with_notebook = sorted(p for p in MODULES if (NOTEBOOKS / f"{p}.ipynb").is_file())
    documents = sorted(p.stem for p in NOTEBOOKS.glob("*.py"))
    notebooks = sorted(
        "/".join(p.relative_to(NOTEBOOKS).with_suffix("").parts)
        for p in NOTEBOOKS.rglob("*.ipynb")
        if ".ipynb_checkpoints" not in p.parts
    )

    assert with_notebook, f"no literate module under {SOURCES}"
    assert with_notebook == WITH_CHECKS
    assert notebooks == sorted(with_notebook + documents)


@pytest.mark.parametrize("check", [c for _, _, c in CHECKS], ids=[f"{p}.{n}" for p, n, _ in CHECKS])
def test_check(check):
    check()


def _figure_modules() -> list[str]:
    return [path for path in WITH_CHECKS if hasattr(_module(path), "save_figures")]


@pytest.mark.parametrize("path", _figure_modules())
def test_figures_render(path, tmp_path):
    paths = _module(path).save_figures(tmp_path)

    assert paths and all(p.is_file() and p.stat().st_size > 0 for p in paths)
