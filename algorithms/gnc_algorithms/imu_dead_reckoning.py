# %% [markdown]
# # Strapdown inertial dead reckoning
#
# Pure dead reckoning for a spacecraft carrying one IMU: the gyro's body-frame angular rate is
# integrated to attitude, the accelerometer's body-frame reading is rotated into the inertial
# frame by that attitude and combined with a point-mass gravity model to integrate to velocity
# and position. No correction, no filter — an attitude error feeds the navigation error directly
# through the frame rotation, which is the coupling this algorithm exists to show.
#
# ## Attitude kinematics
#
# Attitude is the modified Rodrigues parameter (MRP) $\sigma_{BN}$, body frame $B$ with respect
# to inertial frame $N$ (Schaub & Junkins; see `mrp.py`). Its kinematic differential equation,
# given the body-frame angular rate $\omega$:
#
# $$\dot\sigma = \tfrac{1}{4} B(\sigma)\,\omega$$
#
# where $B(\sigma)$ is `mrp.B`. $\sigma$ switches to its shadow set (`mrp.shadow`) whenever
# $|\sigma| > 1$, so it never grows without bound.
#
# ## Translational kinematics
#
# Position and velocity, in the inertial frame, integrate the rotated specific-force reading
# against a point-mass gravity term:
#
# $$\dot r = v \qquad \dot v = C_{NB}(\sigma)\,a_B - \mu \frac{r}{|r|^3}$$
#
# where $C_{NB}(\sigma)$ (`mrp.dcm_NB`) rotates a body-frame vector into the inertial frame,
# $a_B$ is the accelerometer's body-frame reading, and $\mu$ is the gravitational parameter,
# supplied by the host so truth and estimate share the same constant.
#
# ## Integration
#
# One `step()` call advances $(\sigma, r, v)$ by one RK4 step over `dt = sample.t - state.t`,
# with $\omega$ and $a_B$ held constant across the step — the sensor contract's promise of raw
# rates and accelerations, not pre-integrated angles. All three states share the same four
# stages, so an attitude error at any stage immediately biases that stage's rotated
# acceleration: the coupling this module exists to demonstrate.

# %%
from dataclasses import dataclass

import numpy as np

from gnc_algorithms.mrp import B, dcm_NB, shadow

# %% [markdown]
# ## Interface
#
# `ImuSample` is one timestamped, raw body-frame reading. `DeadReckoningState` is the
# estimator's state at one instant.


# %%
@dataclass
class ImuSample:
    t: float  # s
    omega_B: np.ndarray  # (3,) rad/s, body-frame angular rate
    accel_B: np.ndarray  # (3,) m/s^2, body-frame non-gravitational acceleration


@dataclass
class DeadReckoningState:
    t: float
    sigma_BN: np.ndarray  # (3,) MRP, body wrt inertial
    r_N: np.ndarray  # (3,) m, inertial position
    v_N: np.ndarray  # (3,) m/s, inertial velocity


# %% [markdown]
# ## Gravity
#
# $\mu r / |r|^3$, literally, with no special case at $r = 0$: away from the origin this is
# finite for any $\mu$; at the origin it is $0/0$ (NaN) regardless of $\mu$, by design — the
# host supplies a real position.


# %%
def _gravity(r: np.ndarray, mu: float) -> np.ndarray:
    r_norm = float(np.linalg.norm(r))
    return mu * r / r_norm**3


# %% [markdown]
# ## The estimator
#
# `ImuDeadReckoner` holds the current `DeadReckoningState` and advances it one `ImuSample` at a
# time. `step` switches $\sigma$ to the shadow set after the RK4 update, so the stored state
# always has $|\sigma| \le 1$.


# %%
class ImuDeadReckoner:
    """Propagates attitude (MRP), position and velocity from raw body-frame IMU samples."""

    def __init__(
        self, sigma0_BN: np.ndarray, r0_N: np.ndarray, v0_N: np.ndarray, t0: float, mu: float
    ) -> None:
        self._mu = mu
        self._state = DeadReckoningState(
            t=t0,
            sigma_BN=np.array(sigma0_BN, dtype=float),
            r_N=np.array(r0_N, dtype=float),
            v_N=np.array(v0_N, dtype=float),
        )

    @property
    def state(self) -> DeadReckoningState:
        return self._state

    def step(self, sample: ImuSample) -> DeadReckoningState:
        """dt = sample.t - state.t (must be > 0). One RK4 step over dt of the coupled state
        (sigma, r, v) with omega and accel_B held constant: dsigma/dt = 1/4 B(sigma) @ omega;
        dr/dt = v; dv/dt = dcm_NB(sigma) @ accel_B - mu * r / |r|^3. Switches sigma to the
        shadow set when |sigma| > 1 after the step. Returns the new state."""
        dt = sample.t - self._state.t
        if not dt > 0.0:
            raise ValueError(f"dt must be > 0, got {dt}")

        omega = np.asarray(sample.omega_B, dtype=float)
        accel = np.asarray(sample.accel_B, dtype=float)
        mu = self._mu

        def derivs(
            sigma: np.ndarray, r: np.ndarray, v: np.ndarray
        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            sigma_dot = 0.25 * B(sigma) @ omega
            r_dot = v
            v_dot = dcm_NB(sigma) @ accel - _gravity(r, mu)
            return sigma_dot, r_dot, v_dot

        sigma, r, v = self._state.sigma_BN, self._state.r_N, self._state.v_N

        k1 = derivs(sigma, r, v)
        k2 = derivs(sigma + 0.5 * dt * k1[0], r + 0.5 * dt * k1[1], v + 0.5 * dt * k1[2])
        k3 = derivs(sigma + 0.5 * dt * k2[0], r + 0.5 * dt * k2[1], v + 0.5 * dt * k2[2])
        k4 = derivs(sigma + dt * k3[0], r + dt * k3[1], v + dt * k3[2])

        sigma_new = sigma + (dt / 6.0) * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0])
        r_new = r + (dt / 6.0) * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1])
        v_new = v + (dt / 6.0) * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2])

        if np.linalg.norm(sigma_new) > 1.0:
            sigma_new = shadow(sigma_new)

        self._state = DeadReckoningState(t=sample.t, sigma_BN=sigma_new, r_N=r_new, v_N=v_new)
        return self._state


# %% [markdown]
# ## Checks
#
# Each check below documents and verifies one property of `step`, in its own function so no
# check's local variables leak into another's. Defining a function costs nothing, so importing
# this module runs none of them; `run_checks`, at the end of this notebook, calls every one.

# %%
_ZERO3 = np.zeros(3)
# A position away from the origin, so _gravity's r / |r|^3 stays finite in checks that hold
# mu = 0 and don't otherwise care about r_N/v_N (see the Gravity note above).
_AWAY_FROM_ORIGIN = np.array([7.0e6, 0.0, 0.0])


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def _propagate_constant_rate(
    omega_B: np.ndarray,
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
        state = reckoner.step(ImuSample(t=i * dt, omega_B=np.asarray(omega_B), accel_B=_ZERO3))
    return state


# %% [markdown]
# ### Constant rate about one body axis matches the analytic MRP
#
# For a rotation held about a single, fixed body axis, the MRP kinematic equation has a closed
# form: $\sigma(t) = \tan(\theta(t)/4)\,\hat e$, with $\theta(t) = \omega t$. Stepping finely
# should converge to it.


# %%
def check_constant_rate_matches_analytic_mrp() -> None:
    omega = 0.5  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = 1.0

    state = _propagate_constant_rate(omega * axis, total_t, n_steps=2000)

    theta = omega * total_t
    expected = np.tan(theta / 4.0) * axis
    np.testing.assert_allclose(
        state.sigma_BN, expected, atol=1e-6, err_msg="constant-rate MRP does not match tan(theta/4)"
    )


# %% [markdown]
# ### Zero input with zero mu leaves the state unchanged
#
# With `omega_B = 0`, `accel_B = 0` and `mu = 0`, nothing drives any of the three states: the
# next state should equal the current one, with only `t` advancing.


# %%
def check_zero_input_zero_mu_leaves_state_unchanged() -> None:
    sigma0 = np.array([0.1, -0.05, 0.2])
    r0 = np.array([1.0e6, 2.0e6, -3.0e6])
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, r0_N=r0, v0_N=_ZERO3, t0=0.0, mu=0.0)

    state = reckoner.step(ImuSample(t=1.0, omega_B=_ZERO3, accel_B=_ZERO3))

    np.testing.assert_allclose(state.sigma_BN, sigma0, atol=1e-12, err_msg="sigma_BN drifted")
    np.testing.assert_allclose(state.r_N, r0, atol=1e-9, err_msg="r_N drifted")
    np.testing.assert_allclose(state.v_N, _ZERO3, atol=1e-12, err_msg="v_N drifted")
    assert abs(state.t - 1.0) < 1e-12, f"state.t should be 1.0, got {state.t}"


# %% [markdown]
# ### A rotation past 180 degrees switches to the shadow set
#
# $\tan(\theta/4)$ exceeds unit magnitude once $\theta > 180°$; the estimator should switch to
# the shadow set (`mrp.shadow`) at that point, keeping $|\sigma| \le 1$ while still representing
# the same attitude — checked against the DCM from an independent axis-angle formula, not
# `mrp.dcm_NB` itself.


# %%
def check_rotation_past_180_degrees_switches_to_shadow_set() -> None:
    omega = 1.0  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = np.pi * 1.2  # theta = 1.2*pi > pi

    state = _propagate_constant_rate(omega * axis, total_t, n_steps=4000)

    assert np.linalg.norm(state.sigma_BN) <= 1.0, "sigma_BN did not switch to the shadow set"

    theta = omega * total_t
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    skew_axis = _skew(axis)
    expected_dcm_bn = cos_t * np.eye(3) + (1.0 - cos_t) * np.outer(axis, axis) - sin_t * skew_axis

    actual_dcm_bn = dcm_NB(state.sigma_BN).T
    np.testing.assert_allclose(
        actual_dcm_bn,
        expected_dcm_bn,
        atol=1e-5,
        err_msg="shadow-set DCM does not match the axis-angle DCM",
    )


# %% [markdown]
# ### Constant acceleration with zero rate, zero mu, and nonzero r0/v0
#
# With $\omega = 0$ (so $\sigma$, and therefore $C_{NB}$, stays fixed at its initial value) and
# $\mu = 0$ (so gravity drops out), $\dot v$ is the constant rotated acceleration: $v(t) = v_0 +
# a t$ and $r(t) = r_0 + v_0 t + \tfrac12 a t^2$ exactly, which RK4 integrates without error for
# a constant derivative.


# %%
def check_constant_acceleration_gives_analytic_v_and_r() -> None:
    r0 = np.array([1.0e6, -2.0e5, 3.0e5])
    v0 = np.array([10.0, -5.0, 2.0])
    accel = np.array([0.3, -0.1, 0.05])
    total_t = 10.0
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=r0, v0_N=v0, t0=0.0, mu=0.0)

    state = reckoner.step(ImuSample(t=total_t, omega_B=_ZERO3, accel_B=accel))

    np.testing.assert_allclose(
        state.v_N, v0 + accel * total_t, atol=1e-9, err_msg="v_N does not match v0 + a*T"
    )
    np.testing.assert_allclose(
        state.r_N,
        r0 + v0 * total_t + 0.5 * accel * total_t**2,
        atol=1e-6,
        err_msg="r_N does not match r0 + v0*T + 1/2*a*T^2",
    )


# %% [markdown]
# ### The accelerometer is rotated body-to-inertial at a non-trivial attitude
#
# The check above holds $\sigma = 0$, where $C_{NB}(0) = I = C_{NB}(0)^T$, so it cannot tell
# $C_{NB}$ from $C_{BN}$ — a transposed rotation would still pass it. Holding $\omega = 0$ keeps
# $\sigma$ fixed at a 90-degree attitude for the whole step, so an independently computed DCM
# (not `mrp.dcm_NB`) pins which direction `step` actually applies to `accel_B`.


# %%
def check_accelerometer_rotated_at_nontrivial_attitude() -> None:
    axis = np.array([0.0, 0.0, 1.0])
    theta = np.pi / 2.0
    sigma0 = np.tan(theta / 4.0) * axis
    r0 = _AWAY_FROM_ORIGIN
    accel = np.array([1.0, 0.0, 0.0])
    total_t = 10.0

    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, r0_N=r0, v0_N=_ZERO3, t0=0.0, mu=0.0)
    state = reckoner.step(ImuSample(t=total_t, omega_B=_ZERO3, accel_B=accel))

    cos_t, sin_t = np.cos(theta), np.sin(theta)
    skew_axis = _skew(axis)
    # C_NB = C_BN^T; C_BN = cos*I + (1-cos)*axis*axis^T - sin*skew(axis) (as used above).
    expected_c_nb = cos_t * np.eye(3) + (1.0 - cos_t) * np.outer(axis, axis) + sin_t * skew_axis
    expected_v = expected_c_nb @ accel * total_t
    expected_r = r0 + 0.5 * expected_c_nb @ accel * total_t**2

    np.testing.assert_allclose(
        state.v_N, expected_v, atol=1e-9, err_msg="accel_B was rotated by the wrong DCM (v_N)"
    )
    np.testing.assert_allclose(
        state.r_N, expected_r, atol=1e-6, err_msg="accel_B was rotated by the wrong DCM (r_N)"
    )


# %% [markdown]
# ### A quarter circular orbit matches the analytic two-body position
#
# Zero accelerometer input and a nonzero `mu` leave pure two-body motion: a circular orbit
# propagated for a quarter period should land within 1 m of the analytic position at the
# elapsed time actually reached by the discrete steps.


# %%
def check_circular_orbit_matches_analytic_two_body_position() -> None:
    mu = 3.986004418e14  # m^3/s^2, Earth
    radius = 6_871_000.0  # m, ~500 km LEO altitude
    v_circ = np.sqrt(mu / radius)
    n = np.sqrt(mu / radius**3)  # mean motion, rad/s
    period = 2.0 * np.pi / n

    r0 = np.array([radius, 0.0, 0.0])
    v0 = np.array([0.0, v_circ, 0.0])
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=r0, v0_N=v0, t0=0.0, mu=mu)

    dt = 1.0
    n_steps = round((period / 4.0) / dt)
    state = reckoner.state
    for i in range(1, n_steps + 1):
        state = reckoner.step(ImuSample(t=i * dt, omega_B=_ZERO3, accel_B=_ZERO3))

    theta = n * state.t
    expected_r = radius * np.array([np.cos(theta), np.sin(theta), 0.0])
    position_error = np.linalg.norm(state.r_N - expected_r)
    assert position_error < 1.0, f"quarter-orbit position error {position_error} m exceeds 1 m"


# %% [markdown]
# ### The MRP kinematics match the DCM time-derivative identity for a non-aligned rate
#
# Every check above holds $\sigma$ parallel to $\omega$, where `mrp.B`'s cross-product term
# vanishes identically and cannot exercise its sign. $\dot C_{BN} = -[\omega_B\times] C_{BN}$
# holds regardless of attitude parameterization (Schaub & Junkins eq. 3.28); checking a step
# against that independent identity by finite difference, with $\sigma$ and $\omega$ not
# aligned, pins the sign a lone-axis case cannot.


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
    cdot_finite_difference = (c1 - c0) / dt

    skew_omega = _skew(omega)
    expected_cdot = -skew_omega @ c0

    np.testing.assert_allclose(
        cdot_finite_difference,
        expected_cdot,
        atol=1e-3,
        err_msg="MRP kinematics do not match the DCM derivative identity",
    )


# %% [markdown]
# ### A non-positive or NaN dt raises
#
# The sensor contract requires `dt = sample.t - state.t` to be strictly positive; `step` should
# reject `dt <= 0` and `dt = NaN` alike (NaN is not `> 0`, so the same comparison catches it).


# %%
def check_invalid_dt_raises() -> None:
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=_ZERO3, v0_N=_ZERO3, t0=5.0, mu=0.0)
    for bad_t in (5.0, 4.0, float("nan")):
        try:
            reckoner.step(ImuSample(t=bad_t, omega_B=_ZERO3, accel_B=_ZERO3))
        except ValueError:
            continue
        raise AssertionError(f"step() should have raised ValueError for t={bad_t}")


# %% [markdown]
# ## Running the checks
#
# `run_checks` calls every check above and prints a one-line pass summary; it runs under
# `python -m gnc_algorithms.imu_dead_reckoning`, under `jupytext --execute`, and when this
# notebook's cells are run top to bottom interactively — never on a plain import.


# %%
def run_checks() -> None:
    checks = (
        check_constant_rate_matches_analytic_mrp,
        check_zero_input_zero_mu_leaves_state_unchanged,
        check_rotation_past_180_degrees_switches_to_shadow_set,
        check_constant_acceleration_gives_analytic_v_and_r,
        check_accelerometer_rotated_at_nontrivial_attitude,
        check_circular_orbit_matches_analytic_two_body_position,
        check_kinematics_match_dcm_derivative_for_nonaligned_rate,
        check_invalid_dt_raises,
    )
    for check in checks:
        check()
    print(f"imu_dead_reckoning: {len(checks)} checks passed")


if __name__ == "__main__":
    run_checks()
