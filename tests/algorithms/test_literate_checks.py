"""Runs every `check_*` of every literate algorithm module, `algorithms/gnc_algorithms/<name>.py`
imported as `gnc_algorithms.<name>`, and checks that every literate document has its notebook:
each algorithm module and each campaign document `notebooks/<name>.py` pairs with
`notebooks/<name>.ipynb`. Campaign documents are never imported or run here."""

import importlib
import inspect
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "algorithms" / "gnc_algorithms"
NOTEBOOKS = ROOT / "notebooks"


def _module_names() -> list[str]:
    return sorted(p.stem for p in SOURCES.glob("*.py") if p.name != "__init__.py")


def _checks() -> list[tuple[str, str, Callable[[], None]]]:
    found = []
    for name in _module_names():
        module = importlib.import_module(f"gnc_algorithms.{name}")
        for check_name, check in inspect.getmembers(module, inspect.isfunction):
            if check_name.startswith("check_") and check.__module__ == module.__name__:
                found.append((name, check_name, check))
    return found


CHECKS = _checks()


def test_every_literate_document_is_paired_with_a_notebook_and_modules_define_checks():
    names = _module_names()
    campaigns = sorted(p.stem for p in NOTEBOOKS.glob("*.py"))

    assert names, f"no literate module under {SOURCES}"
    assert sorted(names + campaigns) == sorted(p.stem for p in NOTEBOOKS.glob("*.ipynb"))
    assert sorted({module for module, _, _ in CHECKS}) == names


@pytest.mark.parametrize("check", [c for _, _, c in CHECKS], ids=[f"{m}.{n}" for m, n, _ in CHECKS])
def test_check(check):
    check()


def _figure_modules() -> list[str]:
    return [
        name
        for name in _module_names()
        if hasattr(importlib.import_module(f"gnc_algorithms.{name}"), "save_figures")
    ]


@pytest.mark.parametrize("name", _figure_modules())
def test_figures_render(name, tmp_path):
    paths = importlib.import_module(f"gnc_algorithms.{name}").save_figures(tmp_path)

    assert paths and all(p.is_file() and p.stat().st_size > 0 for p in paths)
