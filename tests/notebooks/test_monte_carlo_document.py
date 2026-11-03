"""The Monte Carlo document `notebooks/imu_dead_reckoning_monte_carlo.py` and its settings,
imported without running: importing it runs nothing, its counts come from its two environment
variables, it finds the repository root, and it refuses a run directory holding other than the
requested run count."""

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS = ROOT / "notebooks"
DOCUMENT = NOTEBOOKS / "imu_dead_reckoning_monte_carlo.py"


@pytest.fixture
def document(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    """The document imported as a module, as a script or kernel in `notebooks/` would find its
    support package, with subprocess.run refusing every call and the working directory an empty
    temporary one."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"importing the document ran {args}")

    monkeypatch.syspath_prepend(str(NOTEBOOKS))
    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("monte_carlo_document", DOCUMENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings(document: ModuleType):
    return document.MonteCarloSettings.from_environment(seed=0, duration_s=5700.0)


def test_importing_the_document_runs_nothing(document, tmp_path):
    assert list(tmp_path.iterdir()) == []
    assert not hasattr(document, "settings")


def test_the_counts_default_to_852_runs_and_the_cpu_count(document, monkeypatch):
    monkeypatch.delenv("GNC_MONTE_CARLO_RUNS", raising=False)
    monkeypatch.delenv("GNC_MONTE_CARLO_WORKERS", raising=False)
    monkeypatch.setattr("os.cpu_count", lambda: 6)

    settings = _settings(document)

    assert (settings.runs, settings.workers, settings.seed, settings.duration_s) == (
        852, 6, 0, 5700.0
    )  # fmt: skip
    assert settings.line() == "monte carlo: 852 runs, 6 workers, seed 0, 5700 s per case"


def test_the_environment_sets_both_counts(document, monkeypatch):
    monkeypatch.setenv("GNC_MONTE_CARLO_RUNS", "2")
    monkeypatch.setenv("GNC_MONTE_CARLO_WORKERS", "3")

    assert _settings(document).line() == "monte carlo: 2 runs, 3 workers, seed 0, 5700 s per case"


@pytest.mark.parametrize("variable", ["GNC_MONTE_CARLO_RUNS", "GNC_MONTE_CARLO_WORKERS"])
@pytest.mark.parametrize("value", ["0", "-1", "two", ""])
def test_a_count_that_is_not_a_positive_integer_is_refused_by_name(
    document, monkeypatch, variable, value
):
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError, match=variable):
        _settings(document)


def test_the_repository_root_is_found_from_the_notebooks_directory(document):
    assert document.repository_root(NOTEBOOKS) == ROOT


def test_a_directory_outside_a_checkout_is_refused(document, tmp_path):
    with pytest.raises(RuntimeError, match="no wise-gnc-design checkout"):
        document.repository_root(tmp_path)


def test_a_run_directory_holding_fewer_runs_than_requested_is_refused(
    document, monkeypatch, tmp_path
):
    monkeypatch.setattr(document, "load_run_directory", lambda directory: ["one run"])

    with pytest.raises(RuntimeError, match="holds 1 runs; 2 were requested"):
        document.load_requested(2, tmp_path)
