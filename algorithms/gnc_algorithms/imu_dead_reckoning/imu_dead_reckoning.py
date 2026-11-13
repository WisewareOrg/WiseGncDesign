# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation,-kernelspec
# ---

# %% [markdown]
# # Strapdown inertial dead reckoning
#
# Pure dead reckoning for a spacecraft carrying one IMU: the gyro's body-frame angular rate is
# integrated to attitude, and the accelerometer's body-frame reading is rotated into the
# inertial frame by that attitude and combined with a point-mass gravity model to integrate to
# velocity and position. No measurement corrects the estimate, so an attitude error feeds the
# navigation error directly through the frame rotation.


# %%
"""Strapdown inertial dead reckoning from one IMU."""

import numpy as np
from numba import njit
from wise_dynamics.basilisk import Scenario

from gnc_algorithms.imu_dead_reckoning.gross_check import gross_check
from gnc_cdh.basilisk import AlgorithmModule
from harness.mission import Mission, mission_tests, provides

__all__ = ["ImuDeadReckoner"]

# %load_ext wise_dynamics.notebook


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
# Attitude is the unit quaternion $q = (q_w, q_x, q_y, q_z)$ of body frame $B$ with respect to
# inertial frame $N$ (Hamilton, scalar first): it takes body-frame vectors into the inertial frame,
# $v_N = q \otimes v_B \otimes q^{*}$, and $q$ and $-q$ are the same attitude. Its kinematic
# differential equation, given the body-frame angular rate $\omega = \omega_{BN}$ expressed in $B$:
#
# $$\dot q = \tfrac{1}{2}\, q \otimes (0, \omega)$$
#
# which, written out with $q_v = (q_x, q_y, q_z)$, is
#
# $$\dot q_w = -\tfrac{1}{2}\, q_v \cdot \omega \qquad
# \dot q_v = \tfrac{1}{2}\left(q_w\,\omega + q_v \times \omega\right)$$
#
# The integration drifts $q$ off unit norm at the order of its step error, so the step normalizes
# it. Numba cannot call SciPy, so the kinematics and the rotation matrix below are written out
# here; everything outside the step uses SciPy.


# %%
@njit(cache=True)
def _q_dot(q: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """The attitude kinematics, dq/dt = 1/2 q (x) (0, omega), compiled with numba.

    Args:
        q: (4,) quaternion W X Y Z of the body frame B with respect to the inertial frame N.
        omega: (3,) rad/s, the rate of B with respect to N, in B.

    Returns:
        (4,) dq/dt, 1/s.
    """
    w, v = q[0], q[1:]
    return 0.5 * np.concatenate((np.array([-(v @ omega)]), w * omega + np.cross(v, omega)))


# %% [markdown]
# ## Translational kinematics
#
# Position and velocity, in the inertial frame, integrate the rotated specific-force reading
# against a point-mass gravity term:
#
# $$\dot r = v \qquad \dot v = C_{NB}(q)\,a_B - \mu \frac{r}{|r|^3}$$
#
# where $C_{NB}(q)$ rotates a body-frame vector into the inertial frame,
#
# $$C_{NB}(q) = \begin{pmatrix}
# 1 - 2(q_y^2 + q_z^2) & 2(q_x q_y - q_w q_z) & 2(q_x q_z + q_w q_y) \\
# 2(q_x q_y + q_w q_z) & 1 - 2(q_x^2 + q_z^2) & 2(q_y q_z - q_w q_x) \\
# 2(q_x q_z - q_w q_y) & 2(q_y q_z + q_w q_x) & 1 - 2(q_x^2 + q_y^2)
# \end{pmatrix}$$
#
# $a_B$ is the accelerometer's body-frame reading of non-gravitational acceleration, and $\mu$ is
# the gravitational parameter, supplied by the host so truth and estimate share one constant.


# %%
@njit(cache=True)
def _dcm_NB(q: np.ndarray) -> np.ndarray:
    """The DCM [NB] of a quaternion, rotating a body-frame vector into the inertial frame.

    Args:
        q: (4,) quaternion W X Y Z of the body frame B with respect to the inertial frame N.

    Returns:
        (3, 3) [NB], so that v_N = [NB] v_B.
    """
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


# %%
@njit(cache=True)
def _translational_rates(
    q: np.ndarray, v: np.ndarray, r: np.ndarray, accel: np.ndarray, mu: float
) -> tuple[np.ndarray, np.ndarray]:
    """The translational kinematics, dr/dt = v and dv/dt = C_NB(q) a_B - mu r/|r|^3.

    Args:
        q: (4,) quaternion W X Y Z of the body frame B with respect to the inertial frame N.
        v: (3,) m/s, inertial velocity in N.
        r: (3,) m, inertial position in N.
        accel: (3,) m/s^2, the accelerometer reading a_B, non-gravitational acceleration in B.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        dr/dt ((3,) m/s, in N) and dv/dt ((3,) m/s^2, in N).
    """
    return v, _dcm_NB(q) @ accel - _gravity(r, mu)


# %% [markdown]
# ## One step
#
# One `step()` call advances $x = (q, r, v)$ by one RK4 step of size $h$ = `dt = sample.t -
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
# 3. the normalization, after the update, and the sign that keeps $q_w \ge 0$:
#    $q_{n+1} \leftarrow \pm q_{n+1} / |q_{n+1}|$. The stages integrate $q$ as it stands, unit or
#    not.
#
# All three states share the same four stages, so an attitude error at any stage biases that
# stage's rotated acceleration, the coupling between attitude and navigation error this module
# demonstrates.
#
# In the flight software, `gnc_cdh.basilisk` calls `step()` at 1 Hz, so `dt` is 1 s and each step
# holds one IMU sample across the whole second.


# %%
@njit(cache=True)
def _step(
    q: np.ndarray,
    r: np.ndarray,
    v: np.ndarray,
    omega_P: np.ndarray,
    accel_P: np.ndarray,
    dcm_BP: np.ndarray,
    dt: float,
    mu: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One RK4 step of the state over `dt`, compiled with numba on its first call and cached.

    The readings are rotated into the body frame B and held across the step; q is normalized after
    it, with W >= 0.

    Args:
        q: (4,) quaternion W X Y Z of B with respect to the inertial frame N.
        r: (3,) m, inertial position in N.
        v: (3,) m/s, inertial velocity in N.
        omega_P: (3,) rad/s, the gyro reading, rate of B with respect to N in the IMU platform
            frame P.
        accel_P: (3,) m/s^2, the accelerometer reading, non-gravitational acceleration in P.
        dcm_BP: (3, 3) [BP] = [PB]^T, rotating a P-frame vector into B.
        dt: s, the step.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        The stepped q (unit, W >= 0), r (m, in N) and v (m/s, in N).
    """
    omega = dcm_BP @ omega_P
    accel = dcm_BP @ accel_P

    def derivs(
        q: np.ndarray, r: np.ndarray, v: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The state's time derivative, the readings held.

        Args:
            q: (4,) quaternion W X Y Z of the body frame B with respect to the inertial frame N.
            r: (3,) m, inertial position in N.
            v: (3,) m/s, inertial velocity in N.

        Returns:
            dq/dt ((4,), 1/s), dr/dt ((3,) m/s, in N) and dv/dt ((3,) m/s^2, in N).
        """
        r_dot, v_dot = _translational_rates(q, v, r, accel, mu)
        return _q_dot(q, omega), r_dot, v_dot

    k1 = derivs(q, r, v)
    k2 = derivs(q + 0.5 * dt * k1[0], r + 0.5 * dt * k1[1], v + 0.5 * dt * k1[2])
    k3 = derivs(q + 0.5 * dt * k2[0], r + 0.5 * dt * k2[1], v + 0.5 * dt * k2[2])
    k4 = derivs(q + dt * k3[0], r + dt * k3[1], v + dt * k3[2])

    q_new = q + (dt / 6.0) * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0])
    r_new = r + (dt / 6.0) * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1])
    v_new = v + (dt / 6.0) * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2])
    q_new = q_new / np.linalg.norm(q_new)
    if q_new[0] < 0.0:
        q_new = -q_new
    return q_new, r_new, v_new


# %% [markdown]
# ## Interface
#
# `step` takes one IMU reading as plain arrays by keyword, named as the IMU message's fields, and
# returns the new state as plain arrays, the estimate the host records under these names; the
# estimator holds its state as the same arrays:
#
# | Name | Units | Frame |
# | --- | --- | --- |
# | `t` (in) | s | |
# | `AngVelPlatform` (in) | rad/s, (3,) | rate of B with respect to N, in the IMU platform frame P |
# | `AccelPlatform` (in) | m/s², (3,) | non-gravitational acceleration, in P |
# | `q_BN` (out) | quaternion W X Y Z, (4,), unit, $q_w \ge 0$ | B with respect to N |
# | `r_BN_N` (out) | m, (3,) | inertial position, in N |
# | `v_BN_N` (out) | m/s, (3,) | inertial velocity, in N |
#
# The estimator owns the IMU's mounting, the DCM $[PB]$ with $v_P = [PB]\,v_B$, and rotates
# each reading into the body frame, $v_B = [PB]^T v_P$, before it integrates.


# %% [markdown]
# ## The estimator
#
# `ImuDeadReckoner` holds its state as `t`, `q_BN`, `r_BN_N` and `v_BN_N` and advances it one IMU
# reading at a time. `step` normalizes $q$ after the RK4 update and keeps $q_w \ge 0$.


# %%
class ImuDeadReckoner:
    """Propagates attitude, inertial position and inertial velocity from raw IMU readings."""

    def __init__(
        self,
        q0_BN: np.ndarray,
        r0_N: np.ndarray,
        v0_N: np.ndarray,
        t0: float,
        mu: float,
        dcm_PB: np.ndarray,
    ) -> None:
        """Holds the initial state, `mu` and the mounting.

        Args:
            q0_BN: (4,) quaternion W X Y Z of B with respect to N at `t0`, held with W >= 0.
            r0_N: (3,) m, inertial position in N at `t0`.
            v0_N: (3,) m/s, inertial velocity in N at `t0`.
            t0: s, the time the initial state applies at.
            mu: m^3/s^2, gravitational parameter of the central body.
            dcm_PB: (3, 3) the IMU's mounting [PB], v_P = [PB] v_B.
        """
        self._mu = float(mu)
        self._dcm_BP = np.ascontiguousarray(np.asarray(dcm_PB, dtype=float).T)
        self.t = float(t0)
        q0 = np.asarray(q0_BN, dtype=float)
        self.q_BN = -q0 if q0[0] < 0.0 else q0
        self.r_BN_N = np.asarray(r0_N, dtype=float)
        self.v_BN_N = np.asarray(v0_N, dtype=float)

    def step(
        self, t: float, AngVelPlatform: np.ndarray, AccelPlatform: np.ndarray
    ) -> dict[str, np.ndarray]:
        """Advances the state to `t` by one RK4 step and returns it.

        Args:
            t: s, the reading's time, after `self.t`.
            AngVelPlatform: (3,) rad/s, the gyro reading, rate of B with respect to N in the IMU
                platform frame P.
            AccelPlatform: (3,) m/s^2, the accelerometer reading, non-gravitational acceleration
                in P.

        Returns:
            `q_BN` ((4,) W X Y Z, unit, W >= 0), `r_BN_N` ((3,) m, in N) and `v_BN_N` ((3,) m/s,
            in N), the same arrays the estimator holds.
        """
        self.q_BN, self.r_BN_N, self.v_BN_N = _step(
            self.q_BN,
            self.r_BN_N,
            self.v_BN_N,
            AngVelPlatform,
            AccelPlatform,
            self._dcm_BP,
            t - self.t,
            self._mu,
        )
        self.t = float(t)
        return {"q_BN": self.q_BN, "r_BN_N": self.r_BN_N, "v_BN_N": self.v_BN_N}


# %% [markdown]
# ## The flight software
#
# `dead_reckoner` builds the estimator at t = 0 from a WiseDynamics scenario's initial state and
# hosts it on the scenario's vehicle with `gnc_cdh.basilisk`, the dynamics and the IMU stepping at
# its period.


# %%
@provides("SYS001")
def dead_reckoner(scenario: Scenario) -> AlgorithmModule:
    """The dead reckoner, built at t = 0 from a scenario's initial state, hosted on its vehicle.

    It takes the IMU's mounting from the vehicle it flies on.

    Args:
        scenario: the scenario whose vehicle and initial state the dead reckoner takes.

    Returns:
        The `AlgorithmModule` hosting it.
    """
    initial = scenario.initial_state()
    algorithm = ImuDeadReckoner(
        initial["q0_BN"],
        initial["r0_N"],
        initial["v0_N"],
        t0=0.0,
        mu=scenario.mu_m3_s2["earth"],
        dcm_PB=np.asarray(scenario.vehicle.imu.dcm_PB),
    )
    return AlgorithmModule(algorithm, scenario.vehicle.readers())


# %% [markdown]
# ## The mission
#
# The dead reckoner on the IMU spacecraft, flown through the scenarios the requirements tree names
# (each sets its own duration and case count) and judged by `just judge` on the attitude ladder and
# the velocity and position rungs. Each case also passes the gross check in `gross_check.py`, which
# bounds every error by the growth the case's drawn biases, the IMU noise, the 1 s step and the
# orbit imply.


# %%
MISSION = Mission(
    vehicle="imu_spacecraft",
    fsw=dead_reckoner,
    rungs=("SRS001", "SRS002", "SRS003", "SRS004", "SRS005"),
    scenarios=("TST001", "TST002"),
    check=gross_check,
)

# %%
# %%monte_carlo
globals().update(mission_tests(MISSION))


# %% [markdown]
# ## The errors
#
# The cells below run in the notebook only: the judged rungs, then each error over time for every
# case, computed with the analyzers' own error math.


# %% active="ipynb"
# import matplotlib.pyplot as plt
# from harness.notebook import judge, plots
# from test_attitude_knowledge import attitude_error_rad
# from test_position_knowledge import position_error_m
# from test_velocity_knowledge import velocity_error_m_s
# from wise_dynamics.notebook import load_runs
#
# judge()

# %% active="ipynb"
# runs = load_runs(Test_imu_spacecraft.test_dead_reckoner_leo500)
# data = [{name: values for name, (values, _) in run["datasets"].items()} for run in runs]
# t = data[0]["t_s"]
# errors = {
#     "attitude error (rad)": [
#         attitude_error_rad(d["truth/q_BN"], d["est/q_BN"]) for d in data
#     ],
#     "velocity error (m/s)": [velocity_error_m_s(d["truth/v_N"], d["est/v_BN_N"]) for d in data],
#     "position error (m)": [position_error_m(d["truth/r_N"], d["est/r_BN_N"]) for d in data],
# }
# figure, axes = plt.subplots(3, 1, sharex=True, figsize=(8, 8), layout="constrained")
# for ax, (label, series) in zip(axes, errors.items(), strict=True):
#     for error in series:
#         ax.plot(t, error, color="C0", alpha=0.1)
#     ax.set_ylabel(label)
# axes[-1].set_xlabel("t (s)")
