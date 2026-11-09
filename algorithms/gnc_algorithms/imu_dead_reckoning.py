# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation
#   kernelspec:
#     display_name: wise-gnc-design (3.14.7)
#     language: python
#     name: python3
# ---

# %%

# %% [markdown]
# # Strapdown inertial dead reckoning
#
# Pure dead reckoning for a spacecraft carrying one IMU: the gyro's body-frame angular rate is
# integrated to attitude, and the accelerometer's body-frame reading is rotated into the
# inertial frame by that attitude and combined with a point-mass gravity model to integrate to
# velocity and position. No measurement corrects the estimate, so an attitude error feeds the
# navigation error directly through the frame rotation.


# %%
"""Strapdown inertial dead reckoning from one IMU.

Gyro rates integrate to an MRP attitude; the accelerometer, rotated by that attitude, plus
point-mass gravity integrate to inertial velocity and position.
"""

from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from numba import njit

from gnc_algorithms.mrp import B, dcm_NB, shadow

if TYPE_CHECKING:
    from wise_dynamics.basilisk.scenarios.leo500 import Leo500

    from gnc_cdh.basilisk import AlgorithmModule

__all__ = ["ImuDeadReckoner"]


# %% [markdown]
# ## Gravity
#
# $\mu r / |r|^3$, literally: finite for any $\mu$ away from the origin, and $0/0$ (NaN) at the
# origin, where no spacecraft state lies.


# %%
@njit(cache=True)
def _gravity(r: np.ndarray, mu: float) -> np.ndarray:
    """Point-mass gravity's magnitude term, `mu r / |r|^3`, compiled with numba.

    Args:
        r: (3,) m, position in the inertial frame N.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        (3,) m/s^2 in N, the acceleration's negative: the caller subtracts it.
    """
    r_norm = float(np.linalg.norm(r))
    return mu * r / r_norm**3


# %% [markdown]
# ## Attitude kinematics
#
# Attitude is the modified Rodrigues parameter (MRP) set $\sigma_{BN}$, body frame $B$ with
# respect to inertial frame $N$ (Schaub & Junkins; see `mrp.py`). Its kinematic differential
# equation, given the body-frame angular rate $\omega = \omega_{BN}$ expressed in $B$:
#
# $$\dot\sigma = \tfrac{1}{4} B(\sigma)\,\omega$$
#
# where $B(\sigma)$ is `mrp.B`. $\sigma$ switches to its shadow set (`mrp.shadow`) whenever
# $|\sigma| > 1$, so it stays bounded.


# %%
@njit(cache=True)
def _sigma_dot(sigma: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """The attitude kinematics, dsigma/dt = 1/4 B(sigma) omega, compiled with numba.

    Args:
        sigma: (3,) MRP of the body frame B with respect to the inertial frame N.
        omega: (3,) rad/s, the rate of B with respect to N, in B.

    Returns:
        (3,) dsigma/dt, 1/s.
    """
    return 0.25 * B(sigma) @ omega


# %% [markdown]
# ## Translational kinematics
#
# Position and velocity, in the inertial frame, integrate the rotated specific-force reading
# against a point-mass gravity term:
#
# $$\dot r = v \qquad \dot v = C_{NB}(\sigma)\,a_B - \mu \frac{r}{|r|^3}$$
#
# where $C_{NB}(\sigma)$ (`mrp.dcm_NB`) rotates a body-frame vector into the inertial frame,
# $a_B$ is the accelerometer's body-frame reading of non-gravitational acceleration, and $\mu$
# is the gravitational parameter, supplied by the host so truth and estimate share one constant.


# %%
@njit(cache=True)
def _translational_rates(
    sigma: np.ndarray, v: np.ndarray, r: np.ndarray, accel: np.ndarray, mu: float
) -> tuple[np.ndarray, np.ndarray]:
    """The translational kinematics, dr/dt = v and dv/dt = C_NB(sigma) a_B - mu r/|r|^3.

    Args:
        sigma: (3,) MRP of the body frame B with respect to the inertial frame N.
        v: (3,) m/s, inertial velocity in N.
        r: (3,) m, inertial position in N.
        accel: (3,) m/s^2, the accelerometer reading a_B, non-gravitational acceleration in B.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        dr/dt ((3,) m/s, in N) and dv/dt ((3,) m/s^2, in N).
    """
    return v, dcm_NB(sigma) @ accel - _gravity(r, mu)


# %% [markdown]
# ## One step
#
# One `step()` call advances $x = (\sigma, r, v)$ by one RK4 step of size $h$ = `dt = sample.t -
# state.t`, with the readings held constant across the step: the sensor delivers raw rates and
# accelerations, not pre-integrated angles. The step applies, in order:
#
# 1. the readings rotated into the body frame, with the mounting $[PB]$ below:
#
#    $$\omega = [PB]^T \omega_P \qquad a_B = [PB]^T a_P$$
#
# 2. RK4 over all three states at once, with $f$ the right-hand sides above and $\omega$, $a_B$
#    held:
#
#    $$k_1 = f(x_n) \quad k_2 = f(x_n + \tfrac{h}{2} k_1) \quad k_3 = f(x_n + \tfrac{h}{2} k_2)
#    \quad k_4 = f(x_n + h\,k_3)$$
#
#    $$x_{n+1} = x_n + \tfrac{h}{6}\left(k_1 + 2 k_2 + 2 k_3 + k_4\right)$$
#
# 3. the shadow switch, after the update (`mrp.shadow`): if $|\sigma_{n+1}| > 1$, then
#    $\sigma_{n+1} \leftarrow -\sigma_{n+1} / |\sigma_{n+1}|^2$.
#
# All three states share the same four stages, so an attitude error at any stage biases that
# stage's rotated acceleration, the coupling between attitude and navigation error this module
# demonstrates.
#
# In the flight software, `gnc_cdh.basilisk` calls `step()` at 1 Hz on the simulation's dynamics
# step (50 Hz at its `hi` fidelity, 20 Hz at `med` and `lo`), so `dt` is 1 s and each step holds
# one IMU sample across the whole second.


# %%
@njit(cache=True)
def _step(
    sigma: np.ndarray,
    r: np.ndarray,
    v: np.ndarray,
    omega_P: np.ndarray,
    accel_P: np.ndarray,
    dcm_BP: np.ndarray,
    dt: float,
    mu: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One RK4 step of the state over `dt`, compiled with numba on its first call and cached.

    The readings are rotated into the body frame B and held across the step; sigma switches to its
    shadow set when |sigma| > 1 after it.

    Args:
        sigma: (3,) MRP of B with respect to the inertial frame N.
        r: (3,) m, inertial position in N.
        v: (3,) m/s, inertial velocity in N.
        omega_P: (3,) rad/s, the gyro reading, rate of B with respect to N in the IMU platform
            frame P.
        accel_P: (3,) m/s^2, the accelerometer reading, non-gravitational acceleration in P.
        dcm_BP: (3, 3) [BP] = [PB]^T, rotating a P-frame vector into B.
        dt: s, the step.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        The stepped sigma (MRP, |sigma| <= 1), r (m, in N) and v (m/s, in N), each (3,).
    """
    omega = dcm_BP @ omega_P
    accel = dcm_BP @ accel_P

    def derivs(
        sigma: np.ndarray, r: np.ndarray, v: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The state's time derivative, the readings held.

        Args:
            sigma: (3,) MRP of the body frame B with respect to the inertial frame N.
            r: (3,) m, inertial position in N.
            v: (3,) m/s, inertial velocity in N.

        Returns:
            dsigma/dt ((3,), 1/s), dr/dt ((3,) m/s, in N) and dv/dt ((3,) m/s^2, in N).
        """
        r_dot, v_dot = _translational_rates(sigma, v, r, accel, mu)
        return _sigma_dot(sigma, omega), r_dot, v_dot

    k1 = derivs(sigma, r, v)
    k2 = derivs(sigma + 0.5 * dt * k1[0], r + 0.5 * dt * k1[1], v + 0.5 * dt * k1[2])
    k3 = derivs(sigma + 0.5 * dt * k2[0], r + 0.5 * dt * k2[1], v + 0.5 * dt * k2[2])
    k4 = derivs(sigma + dt * k3[0], r + dt * k3[1], v + dt * k3[2])

    sigma_new = sigma + (dt / 6.0) * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0])
    r_new = r + (dt / 6.0) * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1])
    v_new = v + (dt / 6.0) * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2])
    if np.linalg.norm(sigma_new) > 1.0:
        sigma_new = shadow(sigma_new)
    return sigma_new, r_new, v_new


# %% [markdown]
# ## Interface
#
# `step` takes one IMU reading as plain arrays by keyword, named as the IMU message's fields, and
# returns the new state as plain arrays named in Basilisk's navigation convention; the estimator
# holds its state as the same arrays:
#
# | Name | Units | Frame |
# | --- | --- | --- |
# | `t` (in) | s | |
# | `AngVelPlatform` (in) | rad/s, (3,) | rate of B with respect to N, in the IMU platform frame P |
# | `AccelPlatform` (in) | m/s², (3,) | non-gravitational acceleration, in P |
# | `sigma_BN` (out) | MRP, (3,), \|σ\| ≤ 1 | B with respect to N |
# | `r_BN_N` (out) | m, (3,) | inertial position, in N |
# | `v_BN_N` (out) | m/s, (3,) | inertial velocity, in N |
#
# The estimator owns the IMU's mounting, the DCM $[PB]$ with $v_P = [PB]\,v_B$, and rotates
# each reading into the body frame, $v_B = [PB]^T v_P$, before it integrates.


# %% [markdown]
# ## The estimator
#
# `ImuDeadReckoner` holds its state as `t`, `sigma_BN`, `r_BN_N` and `v_BN_N` and advances it
# one IMU reading at a time. `step` switches $\sigma$ to the shadow set after the RK4 update, so
# the held state always has $|\sigma| \le 1$.


# %%
class ImuDeadReckoner:
    """Propagates attitude, inertial position and inertial velocity from raw IMU readings.

    The readings arrive in the IMU's platform frame; gravity is a point mass of parameter `mu`.
    The estimator holds its state as `t` (s, the time the state applies at), `sigma_BN` ((3,) MRP
    of B with respect to N, |sigma_BN| <= 1), `r_BN_N` ((3,) m, inertial position in N) and
    `v_BN_N` ((3,) m/s, inertial velocity in N).
    """

    def __init__(
        self,
        sigma0_BN: np.ndarray,
        r0_N: np.ndarray,
        v0_N: np.ndarray,
        t0: float,
        mu: float,
        dcm_PB: np.ndarray,
    ) -> None:
        """Holds the initial state, `mu` and the mounting.

        Args:
            sigma0_BN: (3,) MRP of B with respect to N at `t0`.
            r0_N: (3,) m, inertial position in N at `t0`.
            v0_N: (3,) m/s, inertial velocity in N at `t0`.
            t0: s, the time the initial state applies at.
            mu: m^3/s^2, gravitational parameter of the central body.
            dcm_PB: (3, 3) the IMU's mounting [PB], v_P = [PB] v_B.
        """
        self._mu = float(mu)
        self._dcm_BP = np.ascontiguousarray(np.asarray(dcm_PB, dtype=float).T)
        self.t = float(t0)
        self.sigma_BN = np.asarray(sigma0_BN, dtype=float)
        self.r_BN_N = np.asarray(r0_N, dtype=float)
        self.v_BN_N = np.asarray(v0_N, dtype=float)

    def step(
        self, t: float, AngVelPlatform: np.ndarray, AccelPlatform: np.ndarray
    ) -> dict[str, np.ndarray]:
        """Advances the state to `t` by one RK4 step and returns it.

        Over `dt = t - self.t`, with the readings rotated into B and held constant:
        dsigma/dt = 1/4 B(sigma) omega_B; dr/dt = v; dv/dt = dcm_NB(sigma) accel_B - mu r/|r|^3.

        Args:
            t: s, the reading's time, after `self.t`.
            AngVelPlatform: (3,) rad/s, the gyro reading, rate of B with respect to N in the IMU
                platform frame P.
            AccelPlatform: (3,) m/s^2, the accelerometer reading, non-gravitational acceleration
                in P.

        Returns:
            `sigma_BN` (MRP, |sigma| <= 1), `r_BN_N` (m, in N) and `v_BN_N` (m/s, in N), each
            a (3,) array, the same arrays the estimator holds.
        """
        self.sigma_BN, self.r_BN_N, self.v_BN_N = _step(
            self.sigma_BN,
            self.r_BN_N,
            self.v_BN_N,
            AngVelPlatform,
            AccelPlatform,
            self._dcm_BP,
            t - self.t,
            self._mu,
        )
        self.t = float(t)
        return {"sigma_BN": self.sigma_BN, "r_BN_N": self.r_BN_N, "v_BN_N": self.v_BN_N}


# %% [markdown]
# ## Smoke tests
#
# Flight conditions with closed forms check the algorithm alone, with no simulator. pytest
# collects these from this file.


# %%
IMU_DCM_PB = np.eye(3)
"""The flight software's mounting [PB] of the IMU: identity on this spacecraft."""

UNITS = {"sigma_BN": "MRP", "r_BN_N": "m", "v_BN_N": "m/s"}
"""The units of each output in the run file, by its name."""

_ZERO3 = np.zeros(3)
# A position away from the origin for the attitude tests, which hold mu = 0 because gravity
# plays no part in attitude.
_AWAY_FROM_ORIGIN = np.array([7.0e6, 0.0, 0.0])


def _propagate(
    AngVelPlatform: np.ndarray,
    AccelPlatform: np.ndarray,
    total_t: float,
    n_steps: int,
    sigma0: np.ndarray = _ZERO3,
    mu: float = 0.0,
    r0: np.ndarray = _AWAY_FROM_ORIGIN,
    v0: np.ndarray = _ZERO3,
) -> ImuDeadReckoner:
    """A dead reckoner, mounted at identity, stepped `n_steps` equal steps to `total_t`.

    Args:
        AngVelPlatform: (3,) rad/s, the gyro reading held across every step, in the IMU
            platform frame.
        AccelPlatform: (3,) m/s^2, the accelerometer reading held across every step, in that
            frame.
        total_t: s, the time it is stepped to from t = 0.
        n_steps: the number of equal steps.
        sigma0: (3,) MRP, the initial attitude of the body frame with respect to N.
        mu: m^3/s^2, the gravitational parameter.
        r0: (3,) m, the initial inertial position in N.
        v0: (3,) m/s, the initial inertial velocity in N.

    Returns:
        The stepped `ImuDeadReckoner`, holding `t`, `sigma_BN`, `r_BN_N` and `v_BN_N`.
    """
    reckoner = ImuDeadReckoner(sigma0, r0, v0, t0=0.0, mu=mu, dcm_PB=IMU_DCM_PB)
    dt = total_t / n_steps
    for i in range(1, n_steps + 1):
        reckoner.step(t=i * dt, AngVelPlatform=AngVelPlatform, AccelPlatform=AccelPlatform)
    return reckoner


# %% [markdown]
# A constant rate $\omega$ about one fixed axis $\hat e$ has the closed form
#
# $$\sigma(t) = \tan(\omega t / 4)\,\hat e$$


# %%
def test_a_constant_rate_about_one_axis_matches_the_analytic_mrp():
    """A 0.5 rad/s rate about body x for 1 s lands within 1e-6 of sigma = tan(theta/4) x."""
    omega = 0.5  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = 1.0

    state = _propagate(omega * axis, _ZERO3, total_t, n_steps=2000)

    expected = np.tan(omega * total_t / 4.0) * axis
    np.testing.assert_allclose(
        state.sigma_BN, expected, atol=1e-6, err_msg="constant-rate MRP is not tan(theta/4)"
    )


# %% [markdown]
# Past a rotation of $\pi$ the shadow switch keeps $|\sigma| \le 1$, and the attitude still
# matches the axis-angle rotation $C_{NB}(\sigma) = R(\omega t\,\hat e)$ of a constant rate
# $\omega$ about $\hat e$, as SciPy computes it.


# %%
def test_a_rotation_past_180_degrees_switches_to_the_shadow_set():
    """A rotation past 180 degrees switches to the shadow set.

    A 1 rad/s rate about body x for 1.2 pi s keeps |sigma| <= 1, and its DCM matches SciPy's for
    that rotation within 1e-5.
    """
    from scipy.spatial.transform import Rotation

    omega = 1.0  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = np.pi * 1.2  # theta = 1.2 pi > pi

    state = _propagate(omega * axis, _ZERO3, total_t, n_steps=4000)

    assert np.linalg.norm(state.sigma_BN) <= 1.0, "no switch to the shadow set"
    np.testing.assert_allclose(
        dcm_NB(state.sigma_BN).T,
        Rotation.from_rotvec(omega * total_t * axis).as_matrix().T,
        atol=1e-5,
        err_msg="shadow-set DCM differs from the axis-angle DCM",
    )


# %% [markdown]
# With gravity alone ($a_B = 0$), a circular orbit of radius $r_0$ has the mean motion
# $n = \sqrt{\mu / r_0^3}$ and the position
#
# $$r(t) = r_0\,(\cos nt,\ \sin nt,\ 0)$$


# %%
def test_gravity_alone_keeps_a_quarter_circular_orbit_on_the_analytic_position():
    """Gravity alone keeps a quarter circular orbit on its analytic position.

    At 1 s steps over a quarter of a 500 km circular orbit, the position lands within 1 m of the
    analytic one in N.
    """
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
        state.r_BN_N, expected_r, atol=1.0, err_msg="quarter-orbit position error exceeds 1 m"
    )


# %% [markdown]
# The MRP kinematics agree with the direction cosine matrix derivative identity
#
# $$\dot C_{BN} = -[\omega\times]\,C_{BN}$$


# %%
def test_the_kinematics_match_the_dcm_derivative_for_a_nonaligned_rate():
    """The MRP kinematics match the DCM derivative for a non-aligned rate.

    One 1e-5 s step at a 0.3 rad/s rate about z from sigma = (0.1, 0, 0) matches
    dC_BN/dt = -[omega x] C_BN within 1e-3 per entry.
    """
    sigma0 = np.array([0.1, 0.0, 0.0])
    omega = np.array([0.0, 0.0, 0.3])
    reckoner = ImuDeadReckoner(sigma0, _AWAY_FROM_ORIGIN, _ZERO3, t0=0.0, mu=0.0, dcm_PB=IMU_DCM_PB)
    dt = 1e-5

    state = reckoner.step(t=dt, AngVelPlatform=omega, AccelPlatform=_ZERO3)

    c0 = dcm_NB(sigma0).T
    c1 = dcm_NB(state["sigma_BN"]).T
    np.testing.assert_allclose(
        (c1 - c0) / dt,
        -np.cross(omega[:, None], c0, axis=0),
        atol=1e-3,
        err_msg="MRP kinematics differ from the DCM derivative identity",
    )


# %% [markdown]
# ## The Monte Carlo case
#
# `dead_reckoner` builds the estimator at t = 0 from a WiseDynamics scenario's initial state and
# hosts it on the scenario's vehicle with `gnc_cdh.basilisk`, the dynamics stepping at the
# scenario's fidelity. The imports of the simulator and the host are inside the functions that use
# them, so importing this module loads neither.


# %%
def estimate_fields(fsw: "AlgorithmModule") -> dict[str, tuple[Any, str, str]]:
    """The estimate's run-file datasets, `est/<output name>`, one per output of the host module.

    Args:
        fsw: the host module.

    Returns:
        Each dataset path to the `(message, field, units)` it is recorded from.
    """
    return {f"est/{name}": (message, name, UNITS[name]) for name, message in fsw.outputs.items()}


def bound_inputs() -> dict[str, float]:
    """The bound's inputs, for this test and the Monte Carlo notebook alike.

    Returns:
        `gyro_noise_std_rad_s` (rad/s) and `accel_noise_std_m_s2` (m/s^2) from `ImuSpacecraft`,
        `step_s`, the flight software's step `AlgorithmModule.period_s` (s), and `mu`, Earth's
        gravitational parameter from `Leo500` (m^3/s^2).
    """
    from wise_dynamics.basilisk import ImuSpacecraft
    from wise_dynamics.basilisk.scenarios.leo500 import Leo500

    from gnc_cdh.basilisk import AlgorithmModule

    return {
        "gyro_noise_std_rad_s": ImuSpacecraft.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": ImuSpacecraft.accel_noise_std_m_s2,
        "step_s": AlgorithmModule.period_s,
        "mu": Leo500.mu_m3_s2["earth"],
    }


def dead_reckoner(scenario: "Leo500") -> "AlgorithmModule":
    """The dead reckoner, built at t = 0 from a scenario's initial state, hosted on its vehicle.

    Args:
        scenario: the scenario whose vehicle and initial state the dead reckoner takes.

    Returns:
        The `AlgorithmModule` hosting it.
    """
    from wise_dynamics.basilisk.scenarios.leo500 import Leo500

    from gnc_cdh.basilisk import AlgorithmModule

    initial = scenario.initial_state()
    algorithm = ImuDeadReckoner(
        initial["sigma0_BN"],
        initial["r0_N"],
        initial["v0_N"],
        t0=0.0,
        mu=Leo500.mu_m3_s2["earth"],
        dcm_PB=IMU_DCM_PB,
    )
    return AlgorithmModule(algorithm, scenario.vehicle.readers())


# %%
def test_the_estimate_is_written_at_whole_seconds():
    """Run 3.5 s in Leo500, the estimate is last written at 3 s.

    The module runs at its 1 s `period_s`, not at the dynamics step.
    """
    from Basilisk.architecture import messaging
    from wise_dynamics.basilisk.scenarios.leo500 import Leo500

    scenario = Leo500()
    fsw = dead_reckoner(scenario)
    estimate = messaging.NavAttMsgReader()
    estimate.subscribeTo(fsw.output_messages["nav_att"])

    scenario.run(fsw, {}, duration_s=3.5)

    assert estimate.timeWritten() == 3_000_000_000
    assert fsw.algorithm.t == 3.0


# %% [markdown]
# Each case runs the estimator for the scenario's default duration, writes its
# run file and holds the estimate within `gnc_analysis.error_bounds`' bound (`BOUND_FACTOR` times
# the growth the case's drawn biases, the IMU noise, the 1 s step and the orbit imply).


# %%
def campaign(
    fsw: "AlgorithmModule",
    sim_scenario: "Leo500",
    sim_duration_s: float,
    sim_run_file: Callable[..., Path],
) -> None:
    """One Monte Carlo case: runs `fsw` in its scenario and holds every error within its bound.

    Writes the case's run file, with the version of this package, and checks it against bounds
    derived from the case's own drawn IMU biases.

    Args:
        fsw: the host module, from `dead_reckoner`.
        sim_scenario: the case's dispersed scenario, from WiseDynamics' plugin.
        sim_duration_s: s, the case's simulated duration.
        sim_run_file: writes the case's run file and returns its path.
    """
    from gnc_analysis.error_bounds import read_run, violations

    datasets = sim_scenario.run(fsw, estimate_fields(fsw), duration_s=sim_duration_s)
    path = sim_run_file(datasets, {"versions_wise_gnc_design": version("wise-gnc-design")})

    assert violations(read_run(path), **bound_inputs()) == []


# %% [markdown]
# The next cell runs one `campaign` per case, in parallel. Save the notebook, then run it.


# %%
# %load_ext wise_dynamics.notebook


# %%
# %%monte_carlo
@pytest.mark.sim_runs(852)
def test_imu_dead_reckoning_case(
    sim_scenario: "Leo500", sim_duration_s: float, sim_run_file: Callable[..., Path]
) -> None:
    """One Monte Carlo case holds every error within its bound.

    Args:
        sim_scenario: the case's dispersed scenario, from WiseDynamics' plugin.
        sim_duration_s: s, the case's simulated duration.
        sim_run_file: writes the case's run file and returns its path.
    """
    campaign(dead_reckoner(sim_scenario), sim_scenario, sim_duration_s, sim_run_file)


# %% [markdown]
# ## Each error against its bound
#
# The cells below run in the notebook only. They read the run files back with `load_runs`.


# %% active="ipynb"
# import matplotlib.pyplot as plt
# from wise_dynamics.notebook import load_runs
#
# from gnc_analysis.error_bounds import BOUND_FACTOR, bound_ratios, error_growth
#
# runs = [
#     {**run["attrs"], **{name: values for name, (values, _) in run["datasets"].items()}}
#     for run in load_runs("test_imu_dead_reckoning_case")
# ]
# inputs = bound_inputs()
# per_case = [bound_ratios(run, **inputs) for run in runs]
# ratios = {name: np.stack([case[name] for case in per_case]) for name in per_case[0]}
# t = runs[0]["t_s"][1:]
# print("| Bound | Worst ratio | Where | 99.9th pct of per-case worst |")
# print("| --- | --- | --- | --- |")
# for name, r in ratios.items():
#     case, sample = np.unravel_index(np.argmax(r), r.shape)
#     print(
#         f"| {name} | {r.max():.2f} | {t[sample]:.0f} s, case {int(runs[case]['case'])} "
#         f"| {np.percentile(r.max(axis=1), 99.9):.2f} |"
#     )
#
# fig, axes = plt.subplots(len(ratios), 1, sharex=True, figsize=(8, 7))
# for ax, (name, r) in zip(axes, ratios.items(), strict=True):
#     ax.plot(t, r.max(axis=0), label="worst across cases")
#     ax.axhline(BOUND_FACTOR, color="C3", linestyle="--", label="bound factor")
#     ax.set_ylabel(f"{name.split()[0]} ratio")
# axes[0].set_title(f"Error over its derived growth, {len(runs)} cases")
# axes[0].legend()
# axes[-1].set_xlabel("t [s]")
# plt.show()


# %% [markdown]
# ## Final errors


# %% active="ipynb"
# final = {name: [] for name in ("attitude error [rad]", "position error [m]")}
# for run in runs:
#     growth = error_growth(run, **inputs)
#     for name in final:
#         final[name].append(growth[name][0][-1])
# for name, values in final.items():
#     print(f"final {name}: mean {np.mean(values):.4g}, max {np.max(values):.4g}")
