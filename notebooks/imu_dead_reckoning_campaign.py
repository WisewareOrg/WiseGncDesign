# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     notebook_metadata_filter: -jupytext.text_representation
# ---

# %% [markdown]
# # IMU dead reckoning across a Monte Carlo campaign
#
# One run shows how the dead reckoner's error arises: `imu_dead_reckoning.ipynb`, beside this
# notebook, walks through a single case. A campaign shows how large the error is. This
# document flies the dead reckoner, hosted by `gnc_cdh.basilisk`, on WiseDynamics' tumbling IMU
# spacecraft in a campaign of dispersed cases. Each case draws its own initial attitude, body
# rate, gyro bias and accelerometer bias. The document then loads the campaign through
# `gnc_analysis` and shows the ensemble's attitude, position and velocity error, and each
# error against the accuracy bound its case's biases imply.
#
# The campaign is the repository's scenario test, `tests/sim/test_imu_dead_reckoning.py`, run
# by pytest over many cases, so this document runs from a source checkout with the `sim`
# dependency group installed (`uv sync --group sim`). Every case also checks its own bound, and
# pytest's campaign check loads the whole directory before the analysis below begins.
#
# **Run count.** `GNC_CAMPAIGN_RUNS` sets the number of cases (default 852) and
# `GNC_CAMPAIGN_WORKERS` the number of pytest-xdist workers (default the CPU count). Both are
# printed first, beside the seed and the duration of each case.
#
# Each step below is a function; the cells that run them sit under `if __name__ ==
# "__main__":`, which holds in a notebook kernel and under `python
# notebooks/imu_dead_reckoning_campaign.py`, so importing this file runs nothing.

# %%
"""Runs the IMU dead-reckoning scenario as a Monte Carlo campaign and shows its ensemble error
and bound ratios."""

import importlib.util
import io
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from gnc_analysis.error_bounds import BOUND_FACTOR, bound_ratios
from gnc_analysis.navigation_error import metric_figure, summarize, write_report
from gnc_analysis.runs import Run, load_campaign

# %% [markdown]
# A notebook shows a figure through `show`, which renders it as PNG; a script shows nothing,
# and every figure is also saved to the report directory.


# %%
class Inline:
    """`figure` rendered once as PNG, which a notebook front end displays."""

    def __init__(self, figure: Figure) -> None:
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=100)
        self._png = buffer.getvalue()

    def _repr_png_(self) -> bytes:
        return self._png


def show(figure: Figure) -> None:
    """Displays `figure` inline when running in an IPython kernel."""
    if "IPython" in sys.modules:
        from IPython import get_ipython
        from IPython.display import display

        if get_ipython() is not None:
            display(Inline(figure))


# %% [markdown]
# ## Settings
#
# The seed and the duration are fixed: seed 0 and one orbit, 5700 s per case. The run and
# worker counts come from the environment.

# %%
RUNS_VARIABLE = "GNC_CAMPAIGN_RUNS"
WORKERS_VARIABLE = "GNC_CAMPAIGN_WORKERS"
SEED = 0
DURATION_S = 5700.0  # s, one orbit
SCENARIO = "tests/sim/test_imu_dead_reckoning.py"


@dataclass(frozen=True)
class CampaignSettings:
    """What one campaign runs: `runs` cases on `workers` workers, from `seed`, each simulating
    `duration_s` seconds."""

    runs: int
    workers: int
    seed: int
    duration_s: float

    def line(self) -> str:
        """The settings as the one line printed before the campaign runs."""
        return (
            f"campaign: {self.runs} runs, {self.workers} workers, seed {self.seed}, "
            f"{self.duration_s:g} s per case"
        )


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


def campaign_settings() -> CampaignSettings:
    """The campaign's settings: run and worker counts from `GNC_CAMPAIGN_RUNS` (default 852)
    and `GNC_CAMPAIGN_WORKERS` (default the CPU count), seed 0, 5700 s per case.

    Raises:
        ValueError: naming a variable that is set to anything but a positive integer.
    """
    return CampaignSettings(
        runs=_positive_int(RUNS_VARIABLE, 852),
        workers=_positive_int(WORKERS_VARIABLE, os.cpu_count() or 1),
        seed=SEED,
        duration_s=DURATION_S,
    )


if __name__ == "__main__":
    settings = campaign_settings()
    print(settings.line())

# %% [markdown]
# ## Where the campaign runs
#
# pytest runs from the repository root, found by walking up from the working directory, which
# is the root under `python notebooks/imu_dead_reckoning_campaign.py` and `notebooks/` in a
# kernel. The run files go to a fresh directory under `campaign/` and the report to the same
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
    out_dir = root / "campaign" / name
    report_dir = root / "report" / name
    print(f"run files: {out_dir}")
    print(f"report:    {report_dir}")

# %% [markdown]
# ## Running the campaign
#
# pytest runs as a subprocess, so every run of this document starts from a clean interpreter.
# Its output streams into `pytest.log` in the campaign directory, and its last lines are shown
# below, ending with the campaign check. A failed case, a failed campaign check, or a campaign
# holding any number of runs but the one requested stops the document here.


# %%
def run_campaign(settings: CampaignSettings, root: Path, out_dir: Path) -> None:
    """Runs the scenario test as a campaign into `out_dir`, streaming pytest's output to
    `out_dir/pytest.log`, and prints its last lines.

    Raises:
        RuntimeError: carrying those last lines when pytest exits nonzero.
    """
    out_dir.mkdir(parents=True)
    command = [
        sys.executable, "-m", "pytest", SCENARIO, "-q", "-p", "no:cacheprovider",
        "--sim-runs", str(settings.runs), "-n", str(settings.workers),
        "--sim-seed", str(settings.seed), "--sim-duration-s", str(settings.duration_s),
        "--sim-out", str(out_dir),
    ]  # fmt: skip
    log = out_dir / "pytest.log"
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


def load_requested(settings: CampaignSettings, out_dir: Path) -> list[Run]:
    """Loads the campaign in `out_dir`.

    Raises:
        RuntimeError: naming both counts when it holds other than `settings.runs` runs.
    """
    runs = load_campaign(out_dir)
    if len(runs) != settings.runs:
        raise RuntimeError(f"{out_dir} holds {len(runs)} runs; {settings.runs} were requested")
    return runs


if __name__ == "__main__":
    run_campaign(settings, root, out_dir)
    runs = load_requested(settings, out_dir)
    print(f"loaded {len(runs)} runs from {out_dir}")

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


def campaign_ratios(runs: list[Run], inputs: dict[str, float]) -> dict[str, np.ndarray]:
    """Each metric's bound ratio for every run and sample after t = 0, as
    `{metric: (n_runs, N - 1)}`."""
    per_run = [bound_ratios(run, **inputs) for run in runs]
    return {name: np.stack([ratios[name] for ratios in per_run]) for name in per_run[0]}


def ratio_table(runs: list[Run], ratios: dict[str, np.ndarray]) -> str:
    """A Markdown table of each metric's worst ratio, where it occurs, its worst for
    t <= 60 s, and the 99.9th percentile of each run's worst."""
    t = runs[0].t_s[1:]
    lines = [
        "| Bound | Worst, any sample | Where | Worst, t ≤ 60 s | 99.9th pct of per-run worst |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, r in ratios.items():
        run_index, sample = np.unravel_index(np.argmax(r), r.shape)
        lines.append(
            f"| {name} | {r.max():.2f} | {t[sample]:.0f} s, case {runs[run_index].case} "
            f"| {r[:, t <= 60.0].max():.2f} | {np.percentile(r.max(axis=1), 99.9):.2f} |"
        )
    return "\n".join(lines)


def worst_ratio_figure(runs: list[Run], ratios: dict[str, np.ndarray]) -> Figure:
    """Each metric's worst ratio across the ensemble against time, with `BOUND_FACTOR` drawn."""
    t = runs[0].t_s[1:]
    fig = Figure(figsize=(8, 7))
    axes = fig.subplots(len(ratios), 1, sharex=True)
    for ax, (name, r) in zip(axes, ratios.items(), strict=True):
        ax.plot(t, r.max(axis=0), color="C0", label="worst across runs")
        ax.axhline(BOUND_FACTOR, color="C3", linestyle="--", label="bound factor")
        ax.set_ylabel(f"{name.split()[0]} ratio")
    axes[0].set_title(f"Error over its derived growth, {len(runs)} run(s)")
    axes[0].legend()
    axes[-1].set_xlabel("t [s]")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    ratios = campaign_ratios(runs, scenario_bound_inputs(root))
    print(ratio_table(runs, ratios))
    ratio_figure = worst_ratio_figure(runs, ratios)
    ratio_figure.savefig(report_dir / "bound_ratios.png", dpi=150)
    show(ratio_figure)

# %% [markdown]
# ## Summary

# %%
if __name__ == "__main__":
    print(f"summary: {len(runs)} of {settings.runs} requested runs loaded; report in {report_dir}")
    for name, r in ratios.items():
        print(f"{name}: worst ratio {r.max():.2f} against a bound factor of {BOUND_FACTOR:g}")
