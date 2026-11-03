# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     notebook_metadata_filter: -jupytext.text_representation
# ---

# %% [markdown]
# # IMU dead reckoning across a Monte Carlo run
#
# This notebook flies the dead reckoner on WiseDynamics' tumbling IMU spacecraft in Leo500 over
# many dispersed cases. The flight software runs at 1 Hz on a 50 Hz dynamics step. Each case
# draws its own initial attitude, body rate, gyro bias and accelerometer bias.
#
# The dead reckoner itself, its derivation and its code, is `gnc_algorithms.imu_dead_reckoning`.
# This notebook runs four smoke checks of it, then the Monte Carlo run: one pytest session of
# `tests/sim/test_imu_dead_reckoning.py`, so it runs from a source checkout with the `sim` group
# installed (`uv sync --group sim`). Every case checks its own bound. The notebook then reads
# each run file with h5py and shows each error against the bound its case's biases imply, and
# the final errors.
#
# `GNC_MONTE_CARLO_RUNS` sets the number of cases (default 852) and `GNC_MONTE_CARLO_WORKERS`
# the number of pytest-xdist workers (default the CPU count).

# %%
import importlib.util
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from gnc_algorithms.imu_dead_reckoning import DeadReckoningState, ImuDeadReckoner, ImuSample
from gnc_analysis.error_bounds import BOUND_FACTOR, bound_ratios, error_growth, read_run

RUNS = int(os.environ.get("GNC_MONTE_CARLO_RUNS", "852"))
WORKERS = int(os.environ.get("GNC_MONTE_CARLO_WORKERS", str(os.cpu_count() or 1)))
ROOT = next(d for d in (Path.cwd(), *Path.cwd().parents) if (d / "tests" / "sim").is_dir())
SCENARIO = ROOT / "tests" / "sim" / "test_imu_dead_reckoning.py"
RUN_DIR = ROOT / "monte_carlo" / f"imu_dead_reckoning-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
print(f"monte carlo: {RUNS} runs, {WORKERS} workers, run files in {RUN_DIR}")

# %% [markdown]
# ## Smoke checks
#
# Before the Monte Carlo run, four hand checks of flight conditions with closed forms: a
# constant rate about one axis, a rotation past 180 degrees, gravity alone on a circular orbit,
# and a non-aligned rate. Each is its own function, so no check's local variables reach
# another's; the cell after them runs every function whose name starts with `check_`.

# %%
_ZERO3 = np.zeros(3)
# A position away from the origin for the attitude checks, which hold mu = 0 because gravity
# plays no part in attitude.
_AWAY_FROM_ORIGIN = np.array([7.0e6, 0.0, 0.0])


def _skew(v: np.ndarray) -> np.ndarray:
    """The cross-product matrix [~v]."""
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def dcm_NB(sigma: np.ndarray) -> np.ndarray:
    """[NB] of the MRP `sigma` = sigma_BN, with s^2 = |sigma|^2:
    I + (8 [~sigma]^2 + 4 (1 - s^2) [~sigma]) / (1 + s^2)^2."""
    s2 = float(sigma @ sigma)
    sk = _skew(sigma)
    return np.eye(3) + (8.0 * (sk @ sk) + 4.0 * (1.0 - s2) * sk) / (1.0 + s2) ** 2


def _dcm_BN_from_axis_angle(axis: np.ndarray, theta: float) -> np.ndarray:
    """[BN] for B rotated from N by `theta` about unit `axis` (Schaub & Junkins eq. 3.62)."""
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return cos_t * np.eye(3) + (1.0 - cos_t) * np.outer(axis, axis) - sin_t * _skew(axis)


def _propagate(
    omega_B: np.ndarray,
    accel_B: np.ndarray,
    total_t: float,
    n_steps: int,
    sigma0: np.ndarray = _ZERO3,
    mu: float = 0.0,
    r0: np.ndarray = _AWAY_FROM_ORIGIN,
    v0: np.ndarray = _ZERO3,
) -> DeadReckoningState:
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, r0_N=r0, v0_N=v0, t0=0.0, mu=mu)
    dt = total_t / n_steps
    state = reckoner.state
    for i in range(1, n_steps + 1):
        state = reckoner.step(ImuSample(t=i * dt, omega_B=omega_B, accel_B=accel_B))
    return state


# %% [markdown]
# ### Constant rate about one body axis matches the analytic MRP
#
# For a rotation held about a single, fixed body axis, the MRP kinematic equation has a closed
# form: $\sigma(t) = \tan(\theta(t)/4)\,\hat e$, with $\theta(t) = \omega t$. Stepping finely
# converges to it.


# %%
def check_constant_rate_matches_analytic_mrp() -> None:
    omega = 0.5  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = 1.0

    state = _propagate(omega * axis, _ZERO3, total_t, n_steps=2000)

    expected = np.tan(omega * total_t / 4.0) * axis
    np.testing.assert_allclose(
        state.sigma_BN, expected, atol=1e-6, err_msg="constant-rate MRP is not tan(theta/4)"
    )


# %% [markdown]
# ### A rotation past 180 degrees switches to the shadow set
#
# $\tan(\theta/4)$ exceeds unit magnitude once $\theta > 180°$; the estimator switches to the
# shadow set $-\\sigma/|\\sigma|^2$ there, keeping $|\sigma| \le 1$ while representing
# the same attitude — checked against the DCM of an independent axis-angle formula.


# %%
def check_rotation_past_180_degrees_switches_to_shadow_set() -> None:
    omega = 1.0  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = np.pi * 1.2  # theta = 1.2 pi > pi

    state = _propagate(omega * axis, _ZERO3, total_t, n_steps=4000)

    norm = np.linalg.norm(state.sigma_BN)
    if not norm <= 1.0:
        raise AssertionError(f"sigma_BN has norm {norm} > 1: no switch to the shadow set")
    np.testing.assert_allclose(
        dcm_NB(state.sigma_BN).T,
        _dcm_BN_from_axis_angle(axis, omega * total_t),
        atol=1e-5,
        err_msg="shadow-set DCM differs from the axis-angle DCM",
    )


# %% [markdown]
# ### A quarter circular orbit matches the analytic two-body position
#
# Zero accelerometer input and Earth's $\mu$ leave pure two-body motion: a circular orbit
# propagated for a quarter period lands within 1 m of the analytic position at the elapsed
# time the discrete steps reach.


# %%
def check_circular_orbit_matches_analytic_two_body_position() -> None:
    mu = 3.986004418e14  # m^3/s^2, Earth
    radius = 6_871_000.0  # m, about 500 km altitude
    n = np.sqrt(mu / radius**3)  # rad/s, mean motion
    n_steps = round((2.0 * np.pi / n / 4.0) / 1.0)

    state = _propagate(
        _ZERO3,
        _ZERO3,
        total_t=float(n_steps),
        n_steps=n_steps,
        mu=mu,
        r0=np.array([radius, 0.0, 0.0]),
        v0=np.array([0.0, np.sqrt(mu / radius), 0.0]),
    )

    theta = n * state.t
    expected_r = radius * np.array([np.cos(theta), np.sin(theta), 0.0])
    np.testing.assert_allclose(
        state.r_N, expected_r, atol=1.0, err_msg="quarter-orbit position error exceeds 1 m"
    )


# %% [markdown]
# ### The MRP kinematics match the DCM time-derivative identity for a non-aligned rate
#
# The checks above hold $\sigma$ parallel to $\omega$, where $B(\sigma)$'s cross-product term
# vanishes. $\dot C_{BN} = -[\omega_B\times] C_{BN}$ holds for any attitude
# parameterization (Schaub & Junkins eq. 3.28); a finite-difference step with $\sigma$ and
# $\omega$ not aligned pins the sign of that term.


# %%
def check_kinematics_match_dcm_derivative_for_nonaligned_rate() -> None:
    sigma0 = np.array([0.1, 0.0, 0.0])
    omega = np.array([0.0, 0.0, 0.3])
    reckoner = ImuDeadReckoner(
        sigma0_BN=sigma0, r0_N=_AWAY_FROM_ORIGIN, v0_N=_ZERO3, t0=0.0, mu=0.0
    )
    dt = 1e-5

    state = reckoner.step(ImuSample(t=dt, omega_B=omega, accel_B=_ZERO3))

    c0 = dcm_NB(sigma0).T
    c1 = dcm_NB(state.sigma_BN).T
    np.testing.assert_allclose(
        (c1 - c0) / dt,
        -_skew(omega) @ c0,
        atol=1e-3,
        err_msg="MRP kinematics differ from the DCM derivative identity",
    )


# %%
checks = [obj for name, obj in list(globals().items()) if name.startswith("check_")]
for check in checks:
    check()
print(f"{len(checks)} smoke checks passed")


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
         "--sim-runs", str(RUNS), "-n", str(WORKERS), "--sim-out", str(RUN_DIR)],
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

fig = Figure(figsize=(8, 7))
axes = fig.subplots(len(ratios), 1, sharex=True)
for ax, (name, r) in zip(axes, ratios.items(), strict=True):
    ax.plot(t, r.max(axis=0), label="worst across cases")
    ax.axhline(BOUND_FACTOR, color="C3", linestyle="--", label="bound factor")
    ax.set_ylabel(f"{name.split()[0]} ratio")
axes[0].set_title(f"Error over its derived growth, {len(runs)} cases")
axes[0].legend()
axes[-1].set_xlabel("t [s]")
fig.savefig(RUN_DIR / "bound_ratios.png", dpi=150)
fig  # noqa: B018  (a notebook shows the cell's last value)

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
