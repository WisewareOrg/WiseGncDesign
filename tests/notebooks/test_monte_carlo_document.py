"""The Monte Carlo document `notebooks/imu_dead_reckoning_monte_carlo.py`, imported without
running: importing it runs nothing, its counts come from its two environment variables, it finds
the repository root, and it refuses a run directory holding other than the requested run count."""

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "notebooks" / "imu_dead_reckoning_monte_carlo.py"
VARIABLES = ["GNC_MONTE_CARLO_RUNS", "GNC_MONTE_CARLO_WORKERS"]


@pytest.fixture
def document(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    """The document imported as a module, with subprocess.run refusing every call and the
    working directory an empty temporary one."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"importing the document ran {args}")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("monte_carlo_document", DOCUMENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_importing_the_document_runs_nothing(document, tmp_path):
    assert list(tmp_path.iterdir()) == []
    assert not hasattr(document, "runs")


def test_the_counts_default_to_852_runs_and_the_cpu_count(document, monkeypatch):
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(document.os, "cpu_count", lambda: 6)

    runs, workers = document.monte_carlo_runs(), document.monte_carlo_workers()

    assert (runs, workers) == (852, 6)
    assert document.settings_line(runs, workers) == (
        "monte carlo: 852 runs, 6 workers, seed 0, 5700 s per case"
    )


def test_the_environment_sets_both_counts(document, monkeypatch):
    monkeypatch.setenv("GNC_MONTE_CARLO_RUNS", "2")
    monkeypatch.setenv("GNC_MONTE_CARLO_WORKERS", "3")

    assert (document.monte_carlo_runs(), document.monte_carlo_workers()) == (2, 3)


@pytest.mark.parametrize(
    ("variable", "reader"),
    [
        ("GNC_MONTE_CARLO_RUNS", "monte_carlo_runs"),
        ("GNC_MONTE_CARLO_WORKERS", "monte_carlo_workers"),
    ],
)
@pytest.mark.parametrize("value", ["0", "-1", "two", ""])
def test_a_count_that_is_not_a_positive_integer_is_refused_by_name(
    document, monkeypatch, variable, reader, value
):
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError, match=variable):
        getattr(document, reader)()


def test_the_repository_root_is_found_from_the_notebooks_directory(document):
    assert document.repository_root(ROOT / "notebooks") == ROOT


def test_a_directory_outside_a_checkout_is_refused(document, tmp_path):
    with pytest.raises(RuntimeError, match="no wise-gnc-design checkout"):
        document.repository_root(tmp_path)


def test_a_run_directory_holding_fewer_runs_than_requested_is_refused(
    document, monkeypatch, tmp_path
):
    monkeypatch.setattr(document, "load_run_directory", lambda directory: ["one run"])

    with pytest.raises(RuntimeError, match="holds 1 runs; 2 were requested"):
        document.load_requested(2, tmp_path)
