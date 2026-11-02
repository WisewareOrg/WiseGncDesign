# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     notebook_metadata_filter: -jupytext.text_representation
# ---

# %% [markdown]
# # IMU dead reckoning across a Monte Carlo campaign
#
# One run shows how the dead reckoner's error arises (`imu_dead_reckoning.ipynb`); a campaign
# shows how large it is. This document flies the dead reckoner, hosted by `gnc_cdh.basilisk`,
# on WiseDynamics' tumbling IMU spacecraft in a campaign of dispersed cases. Each case draws its
# own initial attitude, body rate, gyro bias and accelerometer bias. The document then loads
# the campaign through `gnc_analysis` and shows the ensemble's attitude, position and velocity
# error, and each error against the accuracy bound its case's biases imply.
#
# The campaign is the repository's scenario test, `tests/sim/test_imu_dead_reckoning.py`, run
# by pytest over many cases, so this document runs from a source checkout with the `sim`
# dependency group installed (`uv sync --group sim`). Every case also checks its own bound, and
# pytest's campaign check loads the whole directory before the analysis below begins.
#
# **Run count.** `GNC_CAMPAIGN_RUNS` sets the number of cases (default 852) and
# `GNC_CAMPAIGN_WORKERS` the number of pytest-xdist workers (default the CPU count). Both are
# printed first, beside the seed and the duration of each case.

# %%
"""Runs the IMU dead-reckoning scenario as a Monte Carlo campaign and shows its ensemble error
and bound ratios."""

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
# A figure is shown by making it a cell's last expression wrapped in `Inline`, which a notebook
# renders as an image.


# %%
class Inline:
    """`figure` rendered once as PNG, which a notebook displays as a cell's last expression."""

    def __init__(self, figure: Figure) -> None:
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=100)
        self._png = buffer.getvalue()

    def _repr_png_(self) -> bytes:
        return self._png


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
        """The settings as one printed line."""
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
# below, ending with the campaign check. A failed case or a failed campaign check stops the
# document here.


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


run_campaign(settings, root, out_dir)
runs = load_campaign(out_dir)
print(f"loaded {len(runs)} runs from {out_dir}")

# %% [markdown]
# ## The ensemble
#
# For each metric, every run is drawn faintly, with the ensemble mean and ±3σ in bold. The
# figures and `summary.md` are also written to the report directory.

# %%
summary = summarize(runs)
write_report(summary, report_dir)
attitude, position, velocity = (metric_figure(summary, s) for s in summary.metrics)
Inline(attitude)

# %%
Inline(position)

# %%
Inline(velocity)

# %% [markdown]
# ## Each error against its bound
#
# Each case's errors stay under `BOUND_FACTOR` (3) times their growth derived from the case's
# drawn IMU biases, the IMU noise and the orbit (`gnc_analysis.error_bounds`). The bound reads
# the plant's noise and step from WiseDynamics' nominal `ImuSpacecraft` configuration and its
# gravitational parameter from a built plant: the same values the scenario's `sim_plant` gives
# every case, since the campaign disperses only initial state and biases.


# %%
def plant_constants() -> dict[str, float]:
    """The bound's plant inputs: gyro and accelerometer noise (per-sample 1-sigma), IMU step in
    s, and the central body's gravitational parameter in m^3/s^2."""
    from wise_dynamics.basilisk import ImuSpacecraft

    config = ImuSpacecraft.nominal()
    return {
        "gyro_noise_std_rad_s": config.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": config.accel_noise_std_m_s2,
        "step_s": config.step_s,
        "mu": ImuSpacecraft().mu,
    }


def campaign_ratios(runs: list[Run], constants: dict[str, float]) -> dict[str, np.ndarray]:
    """Each metric's bound ratio for every run and sample after t = 0, as
    `{metric: (n_runs, N - 1)}`."""
    per_run = [bound_ratios(run, **constants) for run in runs]
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


ratios = campaign_ratios(runs, plant_constants())
print(ratio_table(runs, ratios))
ratio_figure = worst_ratio_figure(runs, ratios)
ratio_figure.savefig(report_dir / "bound_ratios.png", dpi=150)
Inline(ratio_figure)

# %% [markdown]
# ## Summary

# %%
print(settings.line())
print(f"loaded {len(runs)} runs; report in {report_dir}")
for name, r in ratios.items():
    print(f"{name}: worst ratio {r.max():.2f} against a bound factor of {BOUND_FACTOR:g}")
