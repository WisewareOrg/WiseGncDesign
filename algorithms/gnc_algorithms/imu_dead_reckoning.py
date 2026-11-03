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
# respect to inertial frame $N$ (Schaub & Junkins). With $[\tilde\sigma]$ the cross-product
# matrix of $\sigma$ and $s^2 = |\sigma|^2$, its kinematic differential equation, given the
# body-frame angular rate $\omega = \omega_{BN}$ expressed in $B$, is
#
# $$\dot\sigma = \tfrac{1}{4} B(\sigma)\,\omega \qquad
# B(\sigma) = (1 - s^2) I + 2[\tilde\sigma] + 2\sigma\sigma^T$$
#
# $\sigma$ switches to its shadow set $-\sigma/s^2$, the same attitude with the reciprocal norm,
# whenever $|\sigma| > 1$, so it stays bounded.
#
# ## Translational kinematics
#
# Position and velocity, in the inertial frame, integrate the rotated specific-force reading
# against a point-mass gravity term:
#
# $$\dot r = v \qquad \dot v = C_{NB}(\sigma)\,a_B - \mu \frac{r}{|r|^3}$$
#
# where $C_{NB}(\sigma) = I + \frac{8[\tilde\sigma]^2 + 4(1 - s^2)[\tilde\sigma]}{(1 + s^2)^2}$
# rotates a body-frame vector into the inertial frame,
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
# In the flight software, `gnc_cdh.basilisk` calls `step()` at 1 Hz on the simulation's dynamics
# step (50 Hz at its `hi` fidelity, 20 Hz at `med` and `lo`), so `dt` is 1 s and each step holds
# one IMU sample across the whole second.

# %%
"""Strapdown inertial dead reckoning: gyro rates integrated to an MRP attitude, and the
accelerometer, rotated by that attitude, plus point-mass gravity integrated to inertial
velocity and position."""

import math

import numpy as np

from gnc_algorithms.interfaces import DeadReckoningState, ImuSample

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
def _frozen(value: np.ndarray) -> np.ndarray:
    value.setflags(write=False)
    return value


def _vector3(name: str, value: np.ndarray) -> np.ndarray:
    array = np.array(value, dtype=float)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a finite 3-vector, got {value!r}")
    return _frozen(array)


def _components(name: str, value: np.ndarray) -> tuple[float, float, float]:
    """`value`'s three components as floats.

    Raises:
        ValueError: when `value` is not a finite 3-vector.
    """
    if np.shape(value) != (3,):
        raise ValueError(f"{name} must be a finite 3-vector, got {value!r}")
    x, y, z = float(value[0]), float(value[1]), float(value[2])
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        raise ValueError(f"{name} must be a finite 3-vector, got {value!r}")
    return x, y, z


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

        wx, wy, wz = _components("omega_B", sample.omega_B)
        ax, ay, az = _components("accel_B", sample.accel_B)
        mu = self._mu

        def derivs(s1, s2, s3, r1, r2, r3, v1, v2, v3):
            # dsigma/dt = 1/4 B(sigma) omega, B = (1 - s^2) I + 2 [~sigma] + 2 sigma sigma^T.
            ss = s1 * s1 + s2 * s2 + s3 * s3
            c = 1.0 - ss
            sw = s1 * wx + s2 * wy + s3 * wz
            sigma_dot = (
                0.25 * (c * wx + 2.0 * (s2 * wz - s3 * wy) + 2.0 * s1 * sw),
                0.25 * (c * wy + 2.0 * (s3 * wx - s1 * wz) + 2.0 * s2 * sw),
                0.25 * (c * wz + 2.0 * (s1 * wy - s2 * wx) + 2.0 * s3 * sw),
            )
            # C_NB a = a + (8 [~sigma]^2 a + 4 (1 - s^2) [~sigma] a) / (1 + s^2)^2.
            x1, x2, x3 = s2 * az - s3 * ay, s3 * ax - s1 * az, s1 * ay - s2 * ax
            xx1, xx2, xx3 = s2 * x3 - s3 * x2, s3 * x1 - s1 * x3, s1 * x2 - s2 * x1
            d = (1.0 + ss) ** 2
            g = mu / math.sqrt(r1 * r1 + r2 * r2 + r3 * r3) ** 3
            v_dot = (
                ax + (8.0 * xx1 + 4.0 * c * x1) / d - g * r1,
                ay + (8.0 * xx2 + 4.0 * c * x2) / d - g * r2,
                az + (8.0 * xx3 + 4.0 * c * x3) / d - g * r3,
            )
            return (*sigma_dot, v1, v2, v3, *v_dot)

        x = (*self._state.sigma_BN.tolist(), *self._state.r_N.tolist(), *self._state.v_N.tolist())
        h = 0.5 * dt
        k1 = derivs(*x)
        k2 = derivs(*(xi + h * ki for xi, ki in zip(x, k1, strict=True)))
        k3 = derivs(*(xi + h * ki for xi, ki in zip(x, k2, strict=True)))
        k4 = derivs(*(xi + dt * ki for xi, ki in zip(x, k3, strict=True)))
        sixth = dt / 6.0
        new = [
            xi + sixth * (a + 2.0 * b + 2.0 * c + d)
            for xi, a, b, c, d in zip(x, k1, k2, k3, k4, strict=True)
        ]
        sigma_new, r_new, v_new = np.array(new[:3]), np.array(new[3:6]), np.array(new[6:])

        ss_new = float(sigma_new @ sigma_new)
        if math.sqrt(ss_new) > 1.0:
            sigma_new = -sigma_new / ss_new

        self._state = DeadReckoningState(
            t=sample.t, sigma_BN=_frozen(sigma_new), r_N=_frozen(r_new), v_N=_frozen(v_new)
        )
        return self._state
