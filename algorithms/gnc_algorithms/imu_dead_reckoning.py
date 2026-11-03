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
#
# In the flight software, `gnc_cdh.basilisk` calls `step()` at 1 Hz on the simulation's 50 Hz
# dynamics step, so `dt` is 1 s and each step holds one 50 Hz IMU sample across the whole second.

# %%
"""Strapdown inertial dead reckoning: gyro rates integrated to an MRP attitude, and the
accelerometer, rotated by that attitude, plus point-mass gravity integrated to inertial
velocity and position."""

import numpy as np

from gnc_algorithms.interfaces import DeadReckoningState, ImuSample
from gnc_algorithms.mrp import B, dcm_NB, shadow

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
