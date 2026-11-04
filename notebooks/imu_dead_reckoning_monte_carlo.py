# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     notebook_metadata_filter: -jupytext.text_representation
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # IMU dead reckoning across a Monte Carlo run
#
# This notebook flies the dead reckoner on WiseDynamics' tumbling IMU spacecraft in Leo500 over
# many dispersed cases. The flight software runs at 1 Hz on the dynamics step: 50 Hz at `hi`
# fidelity, 20 Hz at `med` and `lo`. Each case draws its own initial attitude, body rate, gyro
# bias and accelerometer bias.
#
# The dead reckoner itself, its derivation and its code, is `gnc_algorithms.imu_dead_reckoning`,
# and all its tests are `tests/sim/test_imu_dead_reckoning.py`: four smoke tests of flight
# conditions with closed forms, its 1 Hz cadence, and the Monte Carlo case. This notebook runs
# that module as one pytest session, so it runs from a source checkout with the `sim` group
# installed (`uv sync --group sim`), and every case checks its own bound. It then reads each run
# file with h5py and shows each error against the bound its case's biases imply, and the final
# errors.
#
# `GNC_MONTE_CARLO_RUNS` sets the number of cases (default 852), `GNC_MONTE_CARLO_WORKERS` the
# number of pytest-xdist workers (default the CPU count), and `GNC_MONTE_CARLO_FIDELITY` the
# simulation's `--sim-fidelity` (default `lo`: RK2 at 0.05 s; `med` is RK4 at 0.05 s, `hi` RK4 at
# 0.02 s).

# %%
"""Runs the dead reckoner's tests and shows each Monte Carlo error against its bound."""

import importlib.util
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from gnc_analysis.error_bounds import BOUND_FACTOR, bound_ratios, error_growth, read_run

RUNS = int(os.environ.get("GNC_MONTE_CARLO_RUNS", "852"))
WORKERS = int(os.environ.get("GNC_MONTE_CARLO_WORKERS", str(os.cpu_count() or 1)))
FIDELITY = os.environ.get("GNC_MONTE_CARLO_FIDELITY", "lo")
ROOT = next(d for d in (Path.cwd(), *Path.cwd().parents) if (d / "tests" / "sim").is_dir())
SCENARIO = ROOT / "tests" / "sim" / "test_imu_dead_reckoning.py"
RUN_DIR = ROOT / "monte_carlo" / f"imu_dead_reckoning-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
print(f"monte carlo: {RUNS} runs, {WORKERS} workers, fidelity {FIDELITY}, run files in {RUN_DIR}")

# %% [markdown]
# ## Running the cases
#
# pytest runs as a subprocess, its output in `pytest.log` in the run directory. A failed case
# stops the notebook here.

# %%
RUN_DIR.mkdir(parents=True)
log = RUN_DIR / "pytest.log"
with log.open("w") as stream:
    status = subprocess.run(
        [sys.executable, "-m", "pytest", str(SCENARIO), "-q", "-p", "no:cacheprovider",
         "--sim-runs", str(RUNS), "-n", str(WORKERS), "--sim-fidelity", FIDELITY,
         "--sim-out", str(RUN_DIR)],
        cwd=ROOT, env={**os.environ, "REQUIRE_SIM": "1"}, stdout=stream, stderr=subprocess.STDOUT,
    ).returncode  # fmt: skip
print("\n".join(log.read_text().splitlines()[-3:]))
if status != 0:
    raise RuntimeError(f"pytest exited {status}; see {log}")
runs = [read_run(path) for path in sorted(RUN_DIR.glob("run_*.h5"))]
if len(runs) != RUNS:
    raise RuntimeError(f"{RUN_DIR} holds {len(runs)} runs; {RUNS} were requested")

# %% [markdown]
# ## Each error against its bound
#
# Each case's errors stay under `BOUND_FACTOR` (3) times their growth derived from the case's
# drawn IMU biases, the IMU noise, the flight software's 1 s step and the orbit
# (`gnc_analysis.error_bounds`). The bound's inputs come from the scenario test's
# `bound_inputs()`.

# %%
spec = importlib.util.spec_from_file_location("scenario", SCENARIO)
scenario = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scenario)
inputs = scenario.bound_inputs()
per_case = [bound_ratios(run, **inputs) for run in runs]
ratios = {name: np.stack([case[name] for case in per_case]) for name in per_case[0]}
t = runs[0]["t_s"][1:]
print("| Bound | Worst ratio | Where | 99.9th pct of per-case worst |")
print("| --- | --- | --- | --- |")
for name, r in ratios.items():
    case, sample = np.unravel_index(np.argmax(r), r.shape)
    print(
        f"| {name} | {r.max():.2f} | {t[sample]:.0f} s, case {int(runs[case]['case'])} "
        f"| {np.percentile(r.max(axis=1), 99.9):.2f} |"
    )

fig, axes = plt.subplots(len(ratios), 1, sharex=True, figsize=(8, 7))
for ax, (name, r) in zip(axes, ratios.items(), strict=True):
    ax.plot(t, r.max(axis=0), label="worst across cases")
    ax.axhline(BOUND_FACTOR, color="C3", linestyle="--", label="bound factor")
    ax.set_ylabel(f"{name.split()[0]} ratio")
axes[0].set_title(f"Error over its derived growth, {len(runs)} cases")
axes[0].legend()
axes[-1].set_xlabel("t [s]")
fig.savefig(RUN_DIR / "bound_ratios.png", dpi=150)
plt.show()

# %% [markdown]
# ## Final errors

# %%
final = {name: [] for name in ("attitude error [rad]", "position error [m]")}
for run in runs:
    growth = error_growth(run, **inputs)
    for name in final:
        final[name].append(growth[name][0][-1])
for name, values in final.items():
    print(f"final {name}: mean {np.mean(values):.4g}, max {np.max(values):.4g}")
passed = sum(all(r.max() <= BOUND_FACTOR for r in case.values()) for case in per_case)
print(f"{passed} of {len(runs)} cases within every bound")
