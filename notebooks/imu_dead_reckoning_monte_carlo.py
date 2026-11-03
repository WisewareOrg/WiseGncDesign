# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     notebook_metadata_filter: -jupytext.text_representation
# ---

# %% [markdown]
# # IMU dead reckoning across a Monte Carlo run
#
# One case shows how the dead reckoner's error arises: `imu_dead_reckoning.ipynb`, beside this
# notebook, walks through a single case. A Monte Carlo run shows how large the error is. This
# document flies the dead reckoner, hosted by `gnc_cdh.basilisk`, on WiseDynamics' tumbling IMU
# spacecraft over many dispersed cases. Each case draws its own initial attitude, body rate,
# gyro bias and accelerometer bias. The document then loads the run files through
# `gnc_analysis` and shows the ensemble's attitude, position and velocity error, and each
# error against the accuracy bound its case's biases imply.
#
# The Monte Carlo run is one pytest session of the repository's scenario test,
# `tests/sim/test_imu_dead_reckoning.py`, over many cases, so this document runs from a source
# checkout with the `sim` dependency group installed (`uv sync --group sim`). Every case checks
# its own bound, and the session check loads the whole run directory before the analysis below
# begins.
#
# **Run count.** `GNC_MONTE_CARLO_RUNS` sets the number of cases (default 852) and
# `GNC_MONTE_CARLO_WORKERS` the number of pytest-xdist workers (default the CPU count). Both
# are printed first, beside the session seed and the duration of each case.
#
# Each step below is a function; the cells that run them sit under `if __name__ ==
# "__main__":`, which holds in a notebook kernel and under `python
# notebooks/imu_dead_reckoning_monte_carlo.py`, so importing this file runs nothing.

# %%
"""Runs the IMU dead-reckoning scenario as a Monte Carlo run of many cases and shows its
ensemble error and bound ratios."""

import importlib.util
import io
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from gnc_analysis.error_bounds import BOUND_FACTOR, bound_ratios
from gnc_analysis.error_metrics import summarize
from gnc_analysis.report import metric_figure, write_report
from gnc_analysis.runs import Run, load_run_directory

# %% [markdown]
# A notebook shows a figure through `show`, which displays it as a PNG image; a script shows
# nothing, and every figure is also saved to the report directory.


# %%
def show(figure: Figure) -> None:
    """Displays `figure` inline when running in an IPython kernel."""
    if "IPython" not in sys.modules:
        return
    from IPython import get_ipython
    from IPython.display import Image, display

    if get_ipython() is not None:
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=100)
        display(Image(data=buffer.getvalue()))


# %% [markdown]
# ## Settings
#
# The session seed and the duration are fixed: seed 0 and one orbit, 5700 s per case. The run
# and worker counts come from the environment.

# %%
RUNS_VARIABLE = "GNC_MONTE_CARLO_RUNS"
WORKERS_VARIABLE = "GNC_MONTE_CARLO_WORKERS"
SEED = 0
DURATION_S = 5700.0  # s, one orbit
SCENARIO = "tests/sim/test_imu_dead_reckoning.py"


def _positive_int(variable: str, default: int) -> int:
    text = os.environ.get(variable)
    if text is None:
        return default
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"{variable} must be a positive integer, got {text!r}")
    return value


def monte_carlo_runs() -> int:
    """The number of cases: `GNC_MONTE_CARLO_RUNS`, default 852.

    Raises:
        ValueError: naming the variable when it is set to anything but a positive integer.
    """
    return _positive_int(RUNS_VARIABLE, 852)


def monte_carlo_workers() -> int:
    """The number of pytest-xdist workers: `GNC_MONTE_CARLO_WORKERS`, default the CPU count.

    Raises:
        ValueError: naming the variable when it is set to anything but a positive integer.
    """
    return _positive_int(WORKERS_VARIABLE, os.cpu_count() or 1)


def settings_line(runs: int, workers: int) -> str:
    """The one line printed before the cases run: their count, the workers, the session seed
    and the duration of each case."""
    return f"monte carlo: {runs} runs, {workers} workers, seed {SEED}, {DURATION_S:g} s per case"


if __name__ == "__main__":
    runs_requested = monte_carlo_runs()
    workers = monte_carlo_workers()
    print(settings_line(runs_requested, workers))

# %% [markdown]
# ## Where the cases run
#
# pytest runs from the repository root, found by walking up from the working directory, which
# is the root under `python notebooks/imu_dead_reckoning_monte_carlo.py` and `notebooks/` in a
# kernel. The run files go to a fresh directory under `monte_carlo/` and the report to the same
# name under `report/`; both directories are ignored by git.


# %%
def repository_root(start: Path) -> Path:
    """The nearest directory at or above `start` whose `pyproject.toml` names
    `wise-gnc-design`.

    Raises:
        RuntimeError: naming `start` when no such directory exists.
    """
    for directory in (start, *start.parents):
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file() and 'name = "wise-gnc-design"' in pyproject.read_text():
            return directory
    raise RuntimeError(f"no wise-gnc-design checkout at or above {start}")


if __name__ == "__main__":
    root = repository_root(Path.cwd().resolve())
    name = f"imu_dead_reckoning-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    run_dir = root / "monte_carlo" / name
    report_dir = root / "report" / name
    print(f"run files: {run_dir}")
    print(f"report:    {report_dir}")

# %% [markdown]
# ## Running the cases
#
# pytest runs as a subprocess, so every run of this document starts from a clean interpreter.
# Its output streams into `pytest.log` in the run directory, and its last lines are shown
# below, ending with the session check. A failed case, a failed session check, or a run
# directory holding any number of runs but the one requested stops the document here.


# %%
def run_cases(runs: int, workers: int, root: Path, run_dir: Path) -> None:
    """Runs the scenario test's `runs` cases on `workers` workers into `run_dir`, streaming
    pytest's output to `run_dir/pytest.log`, and prints its last lines.

    Raises:
        RuntimeError: carrying those last lines when pytest exits nonzero.
    """
    run_dir.mkdir(parents=True)
    command = [
        sys.executable, "-m", "pytest", SCENARIO, "-q", "-p", "no:cacheprovider",
        "--sim-runs", str(runs), "-n", str(workers),
        "--sim-seed", str(SEED), "--sim-duration-s", str(DURATION_S),
        "--sim-out", str(run_dir),
    ]  # fmt: skip
    log = run_dir / "pytest.log"
    with log.open("w") as stream:
        status = subprocess.run(
            command,
            cwd=root,
            env={**os.environ, "REQUIRE_SIM": "1"},
            stdout=stream,
            stderr=subprocess.STDOUT,
        ).returncode
    tail = "\n".join(log.read_text().splitlines()[-12:])
    print(tail)
    if status != 0:
        raise RuntimeError(f"pytest exited {status}; {log} ends:\n{tail}")


def load_requested(requested: int, run_dir: Path) -> list[Run]:
    """Loads the run files in `run_dir`.

    Raises:
        RuntimeError: naming both counts when it holds other than `requested` runs.
    """
    runs = load_run_directory(run_dir)
    if len(runs) != requested:
        raise RuntimeError(f"{run_dir} holds {len(runs)} runs; {requested} were requested")
    return runs


if __name__ == "__main__":
    run_cases(runs_requested, workers, root, run_dir)
    runs = load_requested(runs_requested, run_dir)
    print(f"loaded {len(runs)} runs from {run_dir}")

# %% [markdown]
# ## The ensemble
#
# For each metric, every run is drawn faintly, with the ensemble mean and ±3σ in bold. The
# figures and `summary.md` are also written to the report directory.

# %%
if __name__ == "__main__":
    summary = summarize(runs)
    write_report(summary, report_dir)
    for metric_summary in summary.metrics:
        show(metric_figure(summary, metric_summary))

# %% [markdown]
# ## Each error against its bound
#
# Each case's errors stay under `BOUND_FACTOR` (3) times their growth derived from the case's
# drawn IMU biases, the IMU noise and the orbit (`gnc_analysis.error_bounds`). The bound's
# plant inputs come from the scenario test's own `bound_inputs()`, the one function that
# supplies them to the scenario and to this document.


# %%
def scenario_bound_inputs(root: Path) -> dict[str, float]:
    """The scenario test's `bound_inputs()`: per-sample gyro and accelerometer noise, the IMU
    step in s, and the gravitational parameter in m^3/s^2."""
    spec = importlib.util.spec_from_file_location("imu_dead_reckoning_scenario", root / SCENARIO)
    scenario = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scenario)
    return scenario.bound_inputs()


def case_ratios(runs: list[Run], inputs: dict[str, float]) -> dict[str, np.ndarray]:
    """Each metric's bound ratio for every case and sample after t = 0, as
    `{metric: (n_cases, N - 1)}`."""
    per_case = [bound_ratios(run, **inputs) for run in runs]
    return {name: np.stack([ratios[name] for ratios in per_case]) for name in per_case[0]}


def ratio_table(runs: list[Run], ratios: dict[str, np.ndarray]) -> str:
    """A Markdown table of each metric's worst ratio, where it occurs, its worst for
    t <= 60 s, and the 99.9th percentile of each case's worst."""
    t = runs[0].t_s[1:]
    lines = [
        "| Bound | Worst, any sample | Where | Worst, t ≤ 60 s | 99.9th pct of per-case worst |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, r in ratios.items():
        case_index, sample = np.unravel_index(np.argmax(r), r.shape)
        lines.append(
            f"| {name} | {r.max():.2f} | {t[sample]:.0f} s, case {runs[case_index].case} "
            f"| {r[:, t <= 60.0].max():.2f} | {np.percentile(r.max(axis=1), 99.9):.2f} |"
        )
    return "\n".join(lines)


def worst_ratio_figure(runs: list[Run], ratios: dict[str, np.ndarray]) -> Figure:
    """Each metric's worst ratio across the cases against time, with `BOUND_FACTOR` drawn."""
    t = runs[0].t_s[1:]
    fig = Figure(figsize=(8, 7))
    axes = fig.subplots(len(ratios), 1, sharex=True)
    for ax, (name, r) in zip(axes, ratios.items(), strict=True):
        ax.plot(t, r.max(axis=0), color="C0", label="worst across cases")
        ax.axhline(BOUND_FACTOR, color="C3", linestyle="--", label="bound factor")
        ax.set_ylabel(f"{name.split()[0]} ratio")
    axes[0].set_title(f"Error over its derived growth, {len(runs)} case(s)")
    axes[0].legend()
    axes[-1].set_xlabel("t [s]")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    ratios = case_ratios(runs, scenario_bound_inputs(root))
    print(ratio_table(runs, ratios))
    ratio_figure = worst_ratio_figure(runs, ratios)
    ratio_figure.savefig(report_dir / "bound_ratios.png", dpi=150)
    show(ratio_figure)

# %% [markdown]
# ## Summary

# %%
if __name__ == "__main__":
    print(f"summary: {len(runs)} of {runs_requested} requested runs loaded; report in {report_dir}")
    for name, r in ratios.items():
        print(f"{name}: worst ratio {r.max():.2f} against a bound factor of {BOUND_FACTOR:g}")
