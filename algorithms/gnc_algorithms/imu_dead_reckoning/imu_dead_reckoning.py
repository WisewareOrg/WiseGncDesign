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

from pathlib import Path

import numpy as np
from numba import njit
from wise_dynamics.basilisk import Scenario

import gnc_algorithms.imu_dead_reckoning as package
from gnc_algorithms.imu_dead_reckoning.gross_check import gross_check
from gnc_algorithms.quaternion import dcm_NB, multiply
from gnc_cdh.basilisk import AlgorithmModule
from gnc_cdh.dictionary import Dictionary
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
# it. Numba cannot call SciPy, so the step takes the Hamilton product $\otimes$, and the rotation
# matrix below, from `gnc_algorithms.quaternion`, which tests them against SciPy; everything
# outside the step uses SciPy.


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
    return 0.5 * multiply(q, np.concatenate((np.zeros(1), omega)))


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
    return v, dcm_NB(q) @ accel - _gravity(r, mu)


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
# The estimator plays the F´ instance `nav`. Its contract is `ImuDeadReckoner.fpp` beside this
# notebook, which both builds compile: the F´ build in C++, and this one through the dictionary
# `gnc_cdh.dictionary` generates from it. It boots idle, with no state, and takes one command:
#
# | `nav.initNavState` | Units | Frame |
# | --- | --- | --- |
# | `epoch` | s | the flight software time the state holds at |
# | `attitude` | quaternion W X Y Z, (4,) | B with respect to N |
# | `position` | m, (3,) | inertial position, in N |
# | `velocity` | m/s, (3,) | inertial velocity, in N |
#
# `step` takes one IMU reading as plain arrays by keyword, named as the IMU message's fields:
# `t` (s), `AngVelPlatform` (rad/s, (3,), the rate of B with respect to N in the IMU platform
# frame P) and `AccelPlatform` (m/s², (3,), non-gravitational acceleration in P).
#
# `step` and the command each return the telemetry they write, by channel:
#
# | Channel | Units | Frame |
# | --- | --- | --- |
# | `navState` | `idle`, `initialized` or `propagated` | |
# | `bodyEciAttitude` | quaternion W X Y Z, (4,), unit, $q_w \ge 0$ | B with respect to N |
# | `bodyEciPos` | m, (3,) | inertial position, in N |
# | `bodyEciVel` | m/s, (3,) | inertial velocity, in N |
#
# A write is tagged with the flight software's time when it is written, so the estimator writes a
# value only at a time it holds for: the command writes `navState` alone, since the state it takes
# holds at `epoch`, and each step after it writes the propagated estimate.
#
# The estimator owns the IMU's mounting, the DCM $[PB]$ with $v_P = [PB]\,v_B$, and rotates
# each reading into the body frame, $v_B = [PB]^T v_P$, before it integrates.


# %% [markdown]
# ## The estimator
#
# `ImuDeadReckoner` holds its state as `t`, `q_BN`, `r_BN_N` and `v_BN_N` once commanded, and
# advances it one IMU reading at a time. It holds the commanded $q$ with $q_w \ge 0$, and `step`
# normalizes $q$ after the RK4 update and keeps $q_w \ge 0$.


# %%
class ImuDeadReckoner:
    """Propagates attitude, inertial position and inertial velocity from raw IMU readings."""

    def __init__(self, mu: float, dcm_PB: np.ndarray) -> None:
        """Boots idle, with no state, holding `mu` and the mounting.

        Args:
            mu: m^3/s^2, gravitational parameter of the central body.
            dcm_PB: (3, 3) the IMU's mounting [PB], v_P = [PB] v_B.
        """
        self._mu = float(mu)
        self._dcm_BP = np.ascontiguousarray(np.asarray(dcm_PB, dtype=float).T)
        self.navState = "idle"

    def initNavState(
        self, epoch: float, attitude: np.ndarray, position: np.ndarray, velocity: np.ndarray
    ) -> dict[str, object]:
        """Takes the state as of `epoch`; the next step propagates from there.

        Args:
            epoch: s, the flight software time the state holds at.
            attitude: (4,) quaternion W X Y Z of B with respect to N, held with W >= 0.
            position: (3,) m, inertial position in N.
            velocity: (3,) m/s, inertial velocity in N.

        Returns:
            `navState`, `initialized`.
        """
        q = np.asarray(attitude, dtype=float)
        self.t = float(epoch)
        self.q_BN = -q if q[0] < 0.0 else q
        self.r_BN_N = np.asarray(position, dtype=float)
        self.v_BN_N = np.asarray(velocity, dtype=float)
        self.navState = "initialized"
        return {"navState": self.navState}

    def step(
        self, t: float, AngVelPlatform: np.ndarray, AccelPlatform: np.ndarray
    ) -> dict[str, object]:
        """Advances the state to `t` by one RK4 step, once commanded, and writes it.

        Args:
            t: s, the reading's time.
            AngVelPlatform: (3,) rad/s, the gyro reading, rate of B with respect to N in the IMU
                platform frame P.
            AccelPlatform: (3,) m/s^2, the accelerometer reading, non-gravitational acceleration
                in P.

        Returns:
            `navState`, `idle` until commanded; then also `bodyEciPos` ((3,) m, in N),
            `bodyEciVel` ((3,) m/s, in N) and `bodyEciAttitude` ((4,) W X Y Z, unit, W >= 0).
        """
        if self.navState == "idle":
            return {"navState": self.navState}
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
        self.navState = "propagated"
        return {
            "navState": self.navState,
            "bodyEciPos": self.r_BN_N,
            "bodyEciVel": self.v_BN_N,
            "bodyEciAttitude": self.q_BN,
        }


# %% [markdown]
# ## The flight software
#
# `dead_reckoner` boots the estimator idle and hosts it on the scenario's vehicle as `nav`, with
# `gnc_cdh.basilisk`, held to the dictionary generated from `ImuDeadReckoner.fpp`; the dynamics and
# the IMU step at its period. The scenario's ground procedure gives it its state by command.


# %%
@provides("SYS001")
def dead_reckoner(scenario: Scenario) -> AlgorithmModule:
    """The dead reckoner, booted idle and hosted on a scenario's vehicle as `nav`.

    It takes `mu` from the scenario and the IMU's mounting from the vehicle it flies on.

    Args:
        scenario: the scenario whose vehicle and `mu` the dead reckoner takes.

    Returns:
        The `AlgorithmModule` hosting it.
    """
    algorithm = ImuDeadReckoner(
        mu=scenario.mu_m3_s2["earth"], dcm_PB=np.asarray(scenario.vehicle.imu.dcm_PB)
    )
    dictionary = Dictionary.from_component(
        [Path(package.__file__).with_name("ImuDeadReckoner.fpp")],
        "Gnc.ImuDeadReckoner",
        instance="nav",
    )
    return AlgorithmModule(
        algorithm, scenario.vehicle.readers(), instance="nav", dictionary=dictionary
    )


# %% [markdown]
# ## The mission
#
# The dead reckoner on the IMU spacecraft, flown through the scenarios the requirements tree names
# (each sets its own duration and case count) and judged by `just judge` on the attitude ladder and
# the velocity and position rungs. Each case also passes the gross check in `gross_check.py`, which
# bounds every error by the growth the case's drawn biases, the IMU noise, the 1 s step and the
# orbit imply, from the epoch the ground commanded.


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
# The cells below run in the notebook only: the judged rungs, then each error at every estimate
# the dead reckoner wrote, for every case, computed with the analyzers' own error math against
# truth at each write's time.


# %% active="ipynb"
# import matplotlib.pyplot as plt
# from harness.notebook import judge, plots
# from harness.runs import at
# from test_attitude_knowledge import attitude_error_rad
# from test_position_knowledge import position_error_m
# from test_velocity_knowledge import velocity_error_m_s
# from wise_dynamics.notebook import load_runs
#
# judge()

# %% active="ipynb"
# runs = load_runs(Test_imu_spacecraft.test_dead_reckoner_leo500)
# data = [{name: values for name, (values, _) in run["datasets"].items()} for run in runs]
# metrics = {
#     "attitude error (rad)": ("nav.bodyEciAttitude", "truth/q_BN", attitude_error_rad),
#     "velocity error (m/s)": ("nav.bodyEciVel", "truth/v_N", velocity_error_m_s),
#     "position error (m)": ("nav.bodyEciPos", "truth/r_N", position_error_m),
# }
# figure, axes = plt.subplots(3, 1, sharex=True, figsize=(8, 8), layout="constrained")
# for ax, (label, (channel, truth, error)) in zip(axes, metrics.items(), strict=True):
#     for d in data:
#         t = d[f"tlm_t/{channel}"]
#         ax.plot(t, error(at(d, truth, t), d[f"tlm/{channel}"]), color="C0", alpha=0.1)
#     ax.set_ylabel(label)
# axes[-1].set_xlabel("t (s)")
