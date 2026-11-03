# %% [markdown]
# # Strapdown inertial dead reckoning
#
# Pure dead reckoning for a spacecraft carrying one IMU: the gyro's body-frame angular rate is
# integrated to attitude, and the accelerometer's body-frame reading is rotated into the
# inertial frame by that attitude and combined with a point-mass gravity model to integrate to
# velocity and position. No measurement corrects the estimate, so an attitude error feeds the
# navigation error directly through the frame rotation.
#
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
#
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
#
# ## Integration
#
# One `step()` call advances $(\sigma, r, v)$ by one RK4 step over `dt = sample.t - state.t`,
# with $\omega$ and $a_B$ held constant across the step: the sensor delivers raw rates and
# accelerations, not pre-integrated angles. All three states share the same four stages, so an
# attitude error at any stage biases that stage's rotated acceleration — the coupling between
# attitude and navigation error this module demonstrates.

# %%
"""Strapdown inertial dead reckoning: gyro rates integrated to an MRP attitude, and the
accelerometer, rotated by that attitude, plus point-mass gravity integrated to inertial
velocity and position."""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from gnc_algorithms.interfaces import DeadReckoningState, ImuSample
from gnc_algorithms.mrp import B, dcm_NB, shadow

if TYPE_CHECKING:
    from matplotlib.figure import Figure

__all__ = ["DeadReckoningState", "ImuDeadReckoner", "ImuSample"]

# %% [markdown]
# ## Interface
#
# The estimator takes one `ImuSample` per step and returns a `DeadReckoningState`, both
# immutable values defined in `gnc_algorithms.interfaces`:
#
# | Type | Field | Units | Frame |
# | --- | --- | --- | --- |
# | `ImuSample` | `t` | s | |
# | | `omega_B` | rad/s, (3,) | angular rate of B with respect to N, in B |
# | | `accel_B` | m/s², (3,) | non-gravitational acceleration, in B |
# | `DeadReckoningState` | `t` | s | |
# | | `sigma_BN` | MRP, (3,), \|σ\| ≤ 1 | B with respect to N |
# | | `r_N` | m, (3,) | inertial position |
# | | `v_N` | m/s, (3,) | inertial velocity |
#
# The host rotates the IMU's readings into the body frame before they reach the sample, and the
# state's arrays are read-only.

# %% [markdown]
# ## Gravity
#
# $\mu r / |r|^3$, literally: finite for any $\mu$ away from the origin, and $0/0$ (NaN) at the
# origin, where no spacecraft state lies.


# %%
def _gravity(r: np.ndarray, mu: float) -> np.ndarray:
    r_norm = float(np.linalg.norm(r))
    return mu * r / r_norm**3


def _frozen(value: np.ndarray) -> np.ndarray:
    value.setflags(write=False)
    return value


def _vector3(name: str, value: np.ndarray) -> np.ndarray:
    array = np.array(value, dtype=float)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a finite 3-vector, got {value!r}")
    return _frozen(array)


# %% [markdown]
# ## The estimator
#
# `ImuDeadReckoner` holds the current `DeadReckoningState` and advances it one `ImuSample` at a
# time. `step` switches $\sigma$ to the shadow set after the RK4 update, so the stored state
# always has $|\sigma| \le 1$.


# %%
class ImuDeadReckoner:
    """Propagates attitude (MRP), inertial position and inertial velocity from raw body-frame
    IMU samples, with point-mass gravity of parameter `mu`.

    Args:
        sigma0_BN: (3,) MRP of B with respect to N at `t0`.
        r0_N: (3,) m, inertial position at `t0`.
        v0_N: (3,) m/s, inertial velocity at `t0`.
        t0: s, the time the initial state applies at.
        mu: m^3/s^2, gravitational parameter of the central body, >= 0.

    Raises:
        ValueError: when a vector is not a finite 3-vector, `t0` is not finite, or `mu` is not
            finite and >= 0.
    """

    def __init__(
        self, sigma0_BN: np.ndarray, r0_N: np.ndarray, v0_N: np.ndarray, t0: float, mu: float
    ) -> None:
        if not np.isfinite(t0):
            raise ValueError(f"t0 must be finite, got {t0!r}")
        if not (np.isfinite(mu) and mu >= 0.0):
            raise ValueError(f"mu must be finite and >= 0, got {mu!r}")
        self._mu = float(mu)
        self._state = DeadReckoningState(
            t=float(t0),
            sigma_BN=_vector3("sigma0_BN", sigma0_BN),
            r_N=_vector3("r0_N", r0_N),
            v_N=_vector3("v0_N", v0_N),
        )

    @property
    def state(self) -> DeadReckoningState:
        """The current state."""
        return self._state

    def step(self, sample: ImuSample) -> DeadReckoningState:
        """Advances the state to `sample.t` by one RK4 step and returns the new state.

        Over `dt = sample.t - state.t`, with `omega_B` and `accel_B` held constant:
        dsigma/dt = 1/4 B(sigma) omega_B; dr/dt = v; dv/dt = dcm_NB(sigma) accel_B - mu r/|r|^3.
        Switches sigma to its shadow set when |sigma| > 1 after the step.

        Raises:
            ValueError: when `dt` is not > 0 (including NaN), or `omega_B` or `accel_B` is not a
                finite 3-vector; the state is left unchanged.
        """
        dt = sample.t - self._state.t
        if not dt > 0.0:
            raise ValueError(f"dt must be > 0, got {dt}")

        omega = _vector3("omega_B", sample.omega_B)
        accel = _vector3("accel_B", sample.accel_B)
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

        self._state = DeadReckoningState(
            t=sample.t, sigma_BN=_frozen(sigma_new), r_N=_frozen(r_new), v_N=_frozen(v_new)
        )
        return self._state


# %% [markdown]
# ## Checks
#
# Each check below states and verifies one property of the estimator, in its own function so
# no check's local variables reach another's. `run_checks`, at the end of this notebook, runs
# every function whose name starts with `check_`; importing the module runs none of them.

# %%
_ZERO3 = np.zeros(3)
# A position away from the origin, keeping r / |r|^3 finite in checks that hold mu = 0.
_AWAY_FROM_ORIGIN = np.array([7.0e6, 0.0, 0.0])


def _skew(v: np.ndarray) -> np.ndarray:
    """The checks' own cross-product matrix, kept apart from `mrp`'s as an independent oracle."""
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def _dcm_BN_from_axis_angle(axis: np.ndarray, theta: float) -> np.ndarray:
    """[BN] for B rotated from N by `theta` about unit `axis` (Schaub & Junkins eq. 3.62)."""
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return cos_t * np.eye(3) + (1.0 - cos_t) * np.outer(axis, axis) - sin_t * _skew(axis)


def _relative_angle_deg(dcm1: np.ndarray, dcm2: np.ndarray) -> float:
    """Principal angle, in deg, of [1 2] = [1 N][2 N]^T, from its trace."""
    cos_angle = (np.trace(dcm1 @ dcm2.T) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))


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
# ### Zero input with zero mu leaves the state unchanged
#
# With `omega_B = 0`, `accel_B = 0` and `mu = 0`, nothing drives any of the three states: the
# next state equals the current one, with only `t` advancing.


# %%
def check_zero_input_zero_mu_leaves_state_unchanged() -> None:
    sigma0 = np.array([0.1, -0.05, 0.2])
    r0 = np.array([1.0e6, 2.0e6, -3.0e6])
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, r0_N=r0, v0_N=_ZERO3, t0=0.0, mu=0.0)

    state = reckoner.step(ImuSample(t=1.0, omega_B=_ZERO3, accel_B=_ZERO3))

    np.testing.assert_allclose(state.sigma_BN, sigma0, atol=1e-12, err_msg="sigma_BN drifted")
    np.testing.assert_allclose(state.r_N, r0, atol=1e-9, err_msg="r_N drifted")
    np.testing.assert_allclose(state.v_N, _ZERO3, atol=1e-12, err_msg="v_N drifted")
    np.testing.assert_allclose(state.t, 1.0, atol=1e-12, err_msg="t did not advance to 1.0")


# %% [markdown]
# ### A rotation past 180 degrees switches to the shadow set
#
# $\tan(\theta/4)$ exceeds unit magnitude once $\theta > 180°$; the estimator switches to the
# shadow set (`mrp.shadow`) there, keeping $|\sigma| \le 1$ while representing the same
# attitude — checked against the DCM of an independent axis-angle formula.


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
# ### Constant acceleration with zero rate, zero mu, and nonzero r0/v0
#
# With $\omega = 0$ ($\sigma$, and so $C_{NB}$, fixed at its initial value) and $\mu = 0$
# (no gravity), $\dot v$ is the constant rotated acceleration: $v(t) = v_0 + a t$ and
# $r(t) = r_0 + v_0 t + \tfrac12 a t^2$, which RK4 integrates exactly.


# %%
def check_constant_acceleration_gives_analytic_v_and_r() -> None:
    r0 = np.array([1.0e6, -2.0e5, 3.0e5])
    v0 = np.array([10.0, -5.0, 2.0])
    accel = np.array([0.3, -0.1, 0.05])
    total_t = 10.0
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=r0, v0_N=v0, t0=0.0, mu=0.0)

    state = reckoner.step(ImuSample(t=total_t, omega_B=_ZERO3, accel_B=accel))

    np.testing.assert_allclose(
        state.v_N, v0 + accel * total_t, atol=1e-9, err_msg="v_N is not v0 + a T"
    )
    np.testing.assert_allclose(
        state.r_N,
        r0 + v0 * total_t + 0.5 * accel * total_t**2,
        atol=1e-6,
        err_msg="r_N is not r0 + v0 T + a T^2 / 2",
    )


# %% [markdown]
# ### The accelerometer is rotated body-to-inertial at a non-trivial attitude
#
# At $\sigma = 0$, $C_{NB} = I = C_{NB}^T$, so the check above cannot tell $C_{NB}$ from
# $C_{BN}$. Holding $\omega = 0$ keeps $\sigma$ at a 90-degree attitude for the whole step, so
# an independently computed DCM pins which direction `step` applies to `accel_B`.


# %%
def check_accelerometer_rotated_at_nontrivial_attitude() -> None:
    axis = np.array([0.0, 0.0, 1.0])
    theta = np.pi / 2.0
    sigma0 = np.tan(theta / 4.0) * axis
    accel = np.array([1.0, 0.0, 0.0])
    total_t = 10.0

    reckoner = ImuDeadReckoner(
        sigma0_BN=sigma0, r0_N=_AWAY_FROM_ORIGIN, v0_N=_ZERO3, t0=0.0, mu=0.0
    )
    state = reckoner.step(ImuSample(t=total_t, omega_B=_ZERO3, accel_B=accel))

    accel_N = _dcm_BN_from_axis_angle(axis, theta).T @ accel
    np.testing.assert_allclose(
        state.v_N, accel_N * total_t, atol=1e-9, err_msg="accel_B rotated by the wrong DCM (v_N)"
    )
    np.testing.assert_allclose(
        state.r_N,
        _AWAY_FROM_ORIGIN + 0.5 * accel_N * total_t**2,
        atol=1e-6,
        err_msg="accel_B rotated by the wrong DCM (r_N)",
    )


# %% [markdown]
# ### The accelerometer is rotated by the attitude at every RK4 stage
#
# With $\sigma_0 = 0$, $\mu = 0$, a constant rate $\omega$ about body $+z$ and a constant
# reading $a$ along body $x$, body $x$ turns in the inertial plane, $a_N(t) = a\,[\cos\omega t,
# \sin\omega t, 0]$, which integrates in closed form:
#
# $$v_N(T) = \frac{a}{\omega}\,[\sin\omega T,\ 1 - \cos\omega T,\ 0] \qquad
# r_N(T) = r_0 + \frac{a}{\omega}\left[\frac{1 - \cos\omega T}{\omega},\
# T - \frac{\sin\omega T}{\omega},\ 0\right]$$
#
# Rotating the reading by the step-start attitude in every stage misses it by centimetres per
# second here; the coupled RK4 stays within $10^{-6}$.


# %%
def check_rotating_accelerometer_matches_closed_form() -> None:
    omega = 0.5  # rad/s
    a = 1.0  # m/s^2
    total_t = 10.0

    state = _propagate(np.array([0.0, 0.0, omega]), np.array([a, 0.0, 0.0]), total_t, n_steps=100)

    wt = omega * total_t
    expected_v = (a / omega) * np.array([np.sin(wt), 1.0 - np.cos(wt), 0.0])
    expected_r = _AWAY_FROM_ORIGIN + (a / omega) * np.array(
        [(1.0 - np.cos(wt)) / omega, total_t - np.sin(wt) / omega, 0.0]
    )
    np.testing.assert_allclose(
        state.v_N, expected_v, atol=1e-6, err_msg="rotating accelerometer: v_N"
    )
    np.testing.assert_allclose(
        state.r_N, expected_r, atol=1e-6, err_msg="rotating accelerometer: r_N"
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
# The checks above hold $\sigma$ parallel to $\omega$, where `mrp.B`'s cross-product term
# vanishes. $\dot C_{BN} = -[\omega_B\times] C_{BN}$ holds for any attitude parameterization
# (Schaub & Junkins eq. 3.28); a finite-difference step with $\sigma$ and $\omega$ not aligned
# pins the sign of that term.


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


# %% [markdown]
# ### A non-positive or NaN dt raises
#
# `step` requires `dt = sample.t - state.t` to be strictly positive and rejects `dt <= 0` and
# `dt = NaN` alike.


# %%
def check_invalid_dt_raises() -> None:
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=_ZERO3, v0_N=_ZERO3, t0=5.0, mu=0.0)
    for bad_t in (5.0, 4.0, float("nan")):
        try:
            reckoner.step(ImuSample(t=bad_t, omega_B=_ZERO3, accel_B=_ZERO3))
        except ValueError:
            continue
        raise AssertionError(f"step() accepted t={bad_t} from state t=5.0")


# %% [markdown]
# ### A non-finite or misshapen reading raises and leaves the state unchanged
#
# One NaN reading integrated into the state would corrupt every later step, so `step` rejects a
# reading that is not a finite 3-vector before touching the state.


# %%
def check_invalid_reading_raises_and_keeps_the_state() -> None:
    reckoner = ImuDeadReckoner(
        sigma0_BN=_ZERO3, r0_N=_AWAY_FROM_ORIGIN, v0_N=_ZERO3, t0=0.0, mu=0.0
    )
    before = reckoner.state
    bad_readings = [
        ("omega_B", np.array([0.0, np.nan, 0.0]), _ZERO3),
        ("accel_B", _ZERO3, np.array([np.inf, 0.0, 0.0])),
        ("omega_B", np.zeros(4), _ZERO3),
    ]
    for name, omega_B, accel_B in bad_readings:
        try:
            reckoner.step(ImuSample(t=1.0, omega_B=omega_B, accel_B=accel_B))
        except ValueError as exc:
            if name not in str(exc):
                raise AssertionError(f"error does not name {name}: {exc}") from exc
            if reckoner.state is not before:
                raise AssertionError(f"a rejected {name} changed the state") from exc
            continue
        raise AssertionError(
            f"step() accepted {name}={omega_B if name == 'omega_B' else accel_B!r}"
        )


# %% [markdown]
# ### Invalid construction arguments raise
#
# The constructor accepts finite 3-vectors, a finite `t0` and a finite, non-negative `mu`, and
# raises `ValueError` naming the argument otherwise.


# %%
def check_invalid_construction_raises() -> None:
    good = {"sigma0_BN": _ZERO3, "r0_N": _AWAY_FROM_ORIGIN, "v0_N": _ZERO3, "t0": 0.0, "mu": 0.0}
    bad_values = [
        ("sigma0_BN", np.zeros((3, 1))),
        ("r0_N", np.zeros(4)),
        ("v0_N", np.array([0.0, np.nan, 0.0])),
        ("t0", float("inf")),
        ("mu", -1.0),
        ("mu", float("nan")),
    ]
    for name, value in bad_values:
        try:
            ImuDeadReckoner(**{**good, name: value})
        except ValueError as exc:
            if name not in str(exc):
                raise AssertionError(f"error for {name}={value!r} does not name it: {exc}") from exc
            continue
        raise AssertionError(f"ImuDeadReckoner accepted {name}={value!r}")


# %% [markdown]
# ## A sample run
#
# A worked explanation of one case, not a measure of the error: the dispersed Monte Carlo run
# in `imu_dead_reckoning_monte_carlo.ipynb` is that. Ten minutes in a circular 500 km orbit with a
# 0.3 rad/s tumble: truth (an ideal IMU) against an estimate fed the same motion plus a
# representative constant gyro bias and accelerometer bias, with no correction. The two panels
# show the growing attitude error and position error between them. matplotlib is imported
# here, inside the function, so importing this module needs numpy alone.


# %%
def sample_run_figure() -> "Figure":
    """Propagates truth and a constant-bias estimate over a 600 s orbital tumble and returns a
    `matplotlib.figure.Figure` of attitude error (deg) and position error (m) against time."""
    from matplotlib.figure import Figure

    from gnc_algorithms.mrp import angle, subtract

    mu = 3.986004418e14  # m^3/s^2, Earth
    radius = 6_871_000.0  # m
    r0 = np.array([radius, 0.0, 0.0])
    v0 = np.array([0.0, np.sqrt(mu / radius), 0.0])
    true_omega = np.array([0.0, 0.0, 0.3])  # rad/s
    gyro_bias = np.array([1e-4, -2e-4, 5e-5])  # rad/s
    accel_bias = np.array([1e-4, -5e-5, 2e-4])  # m/s^2

    truth = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=r0, v0_N=v0, t0=0.0, mu=mu)
    estimate = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=r0, v0_N=v0, t0=0.0, mu=mu)

    t_s = np.arange(601, dtype=float)
    attitude_error_deg = np.zeros_like(t_s)
    position_error_m = np.zeros_like(t_s)
    for i, t in enumerate(t_s[1:], start=1):
        true_state = truth.step(ImuSample(t=t, omega_B=true_omega, accel_B=_ZERO3))
        est_state = estimate.step(
            ImuSample(t=t, omega_B=true_omega + gyro_bias, accel_B=accel_bias)
        )
        attitude_error_deg[i] = np.degrees(angle(subtract(true_state.sigma_BN, est_state.sigma_BN)))
        position_error_m[i] = np.linalg.norm(true_state.r_N - est_state.r_N)

    fig = Figure(figsize=(8, 6))
    att_ax, pos_ax = fig.subplots(2, 1, sharex=True)
    att_ax.plot(t_s, attitude_error_deg)
    att_ax.set_ylabel("attitude error [deg]")
    att_ax.set_title("Dead-reckoning error from constant IMU biases")
    pos_ax.plot(t_s, position_error_m)
    pos_ax.set_ylabel("position error [m]")
    pos_ax.set_xlabel("t [s]")
    fig.tight_layout()
    return fig


def save_figures(out_dir: Path) -> list[Path]:
    """Writes this module's figures as PNG files into `out_dir`, creating it if needed, and
    returns their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "imu_dead_reckoning_sample_run.png"
    sample_run_figure().savefig(path)
    return [path]


# %% [markdown]
# ### The sample run matches its closed forms
#
# Each panel of the figure is checked against a closed form, reading the plotted series back.
#
# Attitude: a constant body rate is a rotation about a fixed axis, so truth is $R(\hat z,
# 0.3\,t)$ and the estimate $R(\hat e', |\omega + b_g|\,t)$ with
# $\hat e' = (\omega + b_g)/|\omega + b_g|$; the error is the principal angle of
# $C_{\text{truth}} C_{\text{est}}^T$, matched within $10^{-3}$ deg.
#
# Position: the tumble is about inertial $z$, normal to the orbit plane, so the accelerometer
# bias's $z$ component $a_z$ stays fixed in the inertial frame and drives the out-of-plane
# Clohessy-Wiltshire solution $z(t) = (a_z / n^2)(1 - \cos nt)$. The in-plane components turn
# with the spin and stay within about $|b_\perp| / \omega^2 \approx 1$ mm, and the attitude
# error tilts the bias only to second order, so the error matches $z(t)$ within 5 cm.


# %%
def check_sample_run_matches_closed_forms() -> None:
    fig = sample_run_figure()
    attitude_line, position_line = fig.axes[0].lines[0], fig.axes[1].lines[0]
    t_s = np.asarray(attitude_line.get_xdata())
    attitude_error_deg = np.asarray(attitude_line.get_ydata())
    position_error_m = np.asarray(position_line.get_ydata())
    if t_s.size != 601 or t_s[0] != 0.0:
        raise AssertionError(
            f"sample run has {t_s.size} samples from t = {t_s[0]}, expected 601 from 0"
        )

    true_omega = np.array([0.0, 0.0, 0.3])
    est_omega = true_omega + np.array([1e-4, -2e-4, 5e-5])
    est_axis = est_omega / np.linalg.norm(est_omega)
    expected_deg = [
        _relative_angle_deg(
            _dcm_BN_from_axis_angle(np.array([0.0, 0.0, 1.0]), 0.3 * t),
            _dcm_BN_from_axis_angle(est_axis, np.linalg.norm(est_omega) * t),
        )
        for t in t_s
    ]
    np.testing.assert_allclose(
        attitude_error_deg, expected_deg, atol=1e-3, err_msg="sample-run attitude error"
    )

    n = np.sqrt(3.986004418e14 / 6_871_000.0**3)  # rad/s, mean motion
    expected_m = 2e-4 / n**2 * (1.0 - np.cos(n * t_s))
    np.testing.assert_allclose(
        position_error_m, expected_m, atol=0.05, err_msg="sample-run position error"
    )


# %% [markdown]
# ## Running the checks
#
# `run_checks` runs every `check_*` function above and prints a one-line summary. The checks
# and the figure run only when this module executes as `__main__`: `python -m
# gnc_algorithms.imu_dead_reckoning`, or this notebook's cells run top to bottom in a kernel.
# The figure lands in `figures/` under the working directory.


# %%
def run_checks() -> None:
    """Runs every `check_*` function in this module, in definition order."""
    checks = [obj for name, obj in globals().items() if name.startswith("check_")]
    for check in checks:
        check()
    print(f"imu_dead_reckoning: {len(checks)} checks passed")


if __name__ == "__main__":
    run_checks()
    save_figures(Path("figures"))

# %% [markdown]
# ## Across a Monte Carlo run
#
# One case shows how the error arises. `imu_dead_reckoning_monte_carlo.ipynb`, beside this
# notebook, flies the dead reckoner on a simulated tumbling spacecraft over a dispersed Monte
# Carlo run and shows how large the error is across its cases, against the bound each case's
# IMU biases imply.
