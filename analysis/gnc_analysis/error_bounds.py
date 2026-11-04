"""The Monte Carlo's pass/fail criterion for the IMU dead reckoner.

Each of the estimate's errors against truth, attitude, velocity and position, must stay under
`BOUND_FACTOR` times a growth bound derived from the run's drawn IMU bias, the IMU's noise sigma,
the flight software's step and the orbit's mean motion. At t = 0, where the estimate starts from
truth, each error must be under `ERROR_AT_START`.

A run is one run file as `read_run` returns it. Attitude error is graded with SciPy's `Rotation`,
independently of the dead reckoner's own MRP math.

Each bound is a first-order derivation that holds to 4 orbits, where the position error stays
within about 6% of the orbit radius at the largest drawn bias. With every sensor error zero, the
velocity and position errors stay under 5e-11 m/s and 4e-8 m over an orbit, so the held specific
force needs no term. `BOUND_FACTOR` covers what the leading terms leave out, chiefly the attitude
error rotating the accelerometer bias, which is second order and under 15% of the bias term.
"""

from collections.abc import Mapping
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation

__all__ = [
    "BOUND_FACTOR",
    "ERROR_AT_START",
    "attitude_bound_rad",
    "attitude_error_rad",
    "bound_ratios",
    "error_growth",
    "position_bound_m",
    "position_error_m",
    "read_run",
    "velocity_bound_m_s",
    "velocity_error_m_s",
    "violations",
]

ERROR_AT_START = 1e-9
"""Bound on every error at t = 0, in rad, m and m/s, where the estimate starts from truth."""

BOUND_FACTOR = 3.0
"""Margin on each growth bound, covering the terms its derivation leaves out."""


def read_run(path: str | Path) -> dict[str, np.ndarray]:
    """One run file, read with h5py.

    Args:
        path: the run file.

    Returns:
        Each dataset by its path, `t_s` (s, (N,)) and `truth/*`, `est/*` and `imu/*` ((N, 3)),
        and each root attribute by its name, such as `draw_gyro_bias_P_rad_s`.
    """
    with h5py.File(path, "r") as f:
        run = {name: np.asarray(value) for name, value in f.attrs.items()}
        for group in f.values():
            for name, dataset in group.items() if isinstance(group, h5py.Group) else ():
                run[f"{group.name[1:]}/{name}"] = dataset[()]
        run["t_s"] = f["t_s"][()]
    return run


def attitude_error_rad(sigma_truth_BN: np.ndarray, sigma_est_BN: np.ndarray) -> np.ndarray:
    """The principal angle between truth's attitude and the estimate's at each sample.

    Args:
        sigma_truth_BN: (N, 3) MRP of the body frame B with respect to the inertial frame N.
        sigma_est_BN: (N, 3) the estimate of the same.

    Returns:
        (N,) rad, the magnitude of the rotation from the estimated attitude to the true one.
    """
    truth, estimate = Rotation.from_mrp(sigma_truth_BN), Rotation.from_mrp(sigma_est_BN)
    return (truth * estimate.inv()).magnitude()


def velocity_error_m_s(v_truth_N: np.ndarray, v_est_N: np.ndarray) -> np.ndarray:
    """|v_truth - v_est| at each sample.

    Args:
        v_truth_N: (N, 3) m/s, inertial velocity in the inertial frame N.
        v_est_N: (N, 3) m/s, the estimate of the same.

    Returns:
        (N,) m/s.
    """
    return np.linalg.norm(v_truth_N - v_est_N, axis=-1)


def position_error_m(r_truth_N: np.ndarray, r_est_N: np.ndarray) -> np.ndarray:
    """|r_truth - r_est| at each sample.

    Args:
        r_truth_N: (N, 3) m, inertial position in the inertial frame N.
        r_est_N: (N, 3) m, the estimate of the same.

    Returns:
        (N,) m.
    """
    return np.linalg.norm(r_truth_N - r_est_N, axis=-1)


def attitude_bound_rad(
    t_s: np.ndarray,
    gyro_bias_rad_s: float,
    omega_dot_max_rad_s2: float,
    gyro_noise_std_rad_s: float,
    step_s: float,
) -> np.ndarray:
    """The attitude error's growth bound, `b_g t + 1/2 max|omega_dot| dt t + 3 sigma_g sqrt(t dt)`.

    - A constant gyro bias turns the estimate at most `b_g` faster than truth.
    - Holding each sampled rate over its step while the true rate changes by up to
      `max|omega_dot| dt` leaves at most half that per second.
    - The gyro's white noise is a random walk of `sigma_g sqrt(t dt)` per axis, taken at 3 sigma.

    Args:
        t_s: (N,) s, time since the estimate started from truth.
        gyro_bias_rad_s: `b_g`, rad/s, the norm of the drawn gyro bias.
        omega_dot_max_rad_s2: `max|omega_dot|`, rad/s^2, the true body rate's largest change.
        gyro_noise_std_rad_s: `sigma_g`, rad/s, the gyro's per-sample 1-sigma noise.
        step_s: `dt`, s, the flight software's step.

    Returns:
        (N,) rad.
    """
    t, dt = t_s, step_s
    return (
        gyro_bias_rad_s * t
        + 0.5 * omega_dot_max_rad_s2 * dt * t
        + 3.0 * gyro_noise_std_rad_s * np.sqrt(t * dt)
    )


def velocity_bound_m_s(
    t_s: np.ndarray,
    accel_bias_m_s2: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mean_motion_rad_s: float,
) -> np.ndarray:
    """The velocity error's growth bound, `(1 + (n t)^2 / 3) (b_a t + 3 sigma_a sqrt(t dt))`.

    - A constant accelerometer bias adds `b_a t`; its white noise is a random walk of
      `sigma_a sqrt(t dt)`, taken at 3 sigma.
    - Gravity is evaluated at the estimated position, so the position error feeds back through
      the gravity gradient, whose largest eigenvalue is `2 n^2`. The factor `1 + (n t)^2 / 3` is
      that feedback to first order; the linearized worst case over any bias-direction history is
      within 1.03 times it, verified to 4 orbits.

    Args:
        t_s: (N,) s, time since the estimate started from truth.
        accel_bias_m_s2: `b_a`, m/s^2, the norm of the drawn accelerometer bias.
        accel_noise_std_m_s2: `sigma_a`, m/s^2, the accelerometer's per-sample 1-sigma noise.
        step_s: `dt`, s, the flight software's step.
        mean_motion_rad_s: `n`, rad/s, the orbit's mean motion.

    Returns:
        (N,) m/s.
    """
    t, dt, n = t_s, step_s, mean_motion_rad_s
    return (1.0 + (n * t) ** 2 / 3.0) * (
        accel_bias_m_s2 * t + 3.0 * accel_noise_std_m_s2 * np.sqrt(t * dt)
    )


def position_bound_m(
    t_s: np.ndarray,
    accel_bias_m_s2: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mean_motion_rad_s: float,
) -> np.ndarray:
    """The position error's growth bound,
    `(1 + (n t)^2 / 6) (b_a t^2 / 2 + 3 sigma_a sqrt(dt / 3) t^(3/2))`.

    - A constant accelerometer bias gives `b_a t^2 / 2`; the accelerometer's random walk
      integrates to `sigma_a sqrt(dt / 3) t^(3/2)`, taken at 3 sigma.
    - The factor `1 + (n t)^2 / 6` is the gravity-gradient feedback to first order. Without it the
      along-track secular growth reaches 3.29 times `b_a t^2 / 2` for the worst bias-direction
      history; with it the linearized worst case is within 1.002 times, verified to 4 orbits.

    Args:
        t_s: (N,) s, time since the estimate started from truth.
        accel_bias_m_s2: `b_a`, m/s^2, the norm of the drawn accelerometer bias.
        accel_noise_std_m_s2: `sigma_a`, m/s^2, the accelerometer's per-sample 1-sigma noise.
        step_s: `dt`, s, the flight software's step.
        mean_motion_rad_s: `n`, rad/s, the orbit's mean motion.

    Returns:
        (N,) m.
    """
    t, dt, n = t_s, step_s, mean_motion_rad_s
    return (1.0 + (n * t) ** 2 / 6.0) * (
        0.5 * accel_bias_m_s2 * t**2 + 3.0 * accel_noise_std_m_s2 * np.sqrt(dt / 3.0) * t**1.5
    )


def error_growth(
    run: Mapping[str, np.ndarray],
    gyro_noise_std_rad_s: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mu: float,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each of a run's errors beside its growth bound.

    The bounds take the run's drawn biases, `draw_gyro_bias_P_rad_s` and
    `draw_accel_bias_P_m_s2`; the largest change of its true body rate, `truth/omega_BN_B`; and
    its mean motion `n = sqrt(mu / |r0|^3)`, from `truth/r_N` at t = 0.

    Args:
        run: one run, as `read_run` returns it.
        gyro_noise_std_rad_s: rad/s, the gyro's per-sample 1-sigma noise.
        accel_noise_std_m_s2: m/s^2, the accelerometer's per-sample 1-sigma noise.
        step_s: s, the flight software's step.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        `{metric: (error, bound)}` for `"attitude error [rad]"`, `"velocity error [m/s]"` and
        `"position error [m]"`, each a pair of (N,) arrays over `t_s`.
    """
    t = run["t_s"]
    omega_dot = np.linalg.norm(np.diff(run["truth/omega_BN_B"], axis=0), axis=1) / np.diff(t)
    accel_bias = float(np.linalg.norm(run["draw_accel_bias_P_m_s2"]))
    n = np.sqrt(mu / float(np.linalg.norm(run["truth/r_N"][0])) ** 3)
    return {
        "attitude error [rad]": (
            attitude_error_rad(run["truth/sigma_BN"], run["est/sigma_BN"]),
            attitude_bound_rad(
                t,
                float(np.linalg.norm(run["draw_gyro_bias_P_rad_s"])),
                omega_dot.max(),
                gyro_noise_std_rad_s,
                step_s,
            ),
        ),
        "velocity error [m/s]": (
            velocity_error_m_s(run["truth/v_N"], run["est/v_N"]),
            velocity_bound_m_s(t, accel_bias, accel_noise_std_m_s2, step_s, n),
        ),
        "position error [m]": (
            position_error_m(run["truth/r_N"], run["est/r_N"]),
            position_bound_m(t, accel_bias, accel_noise_std_m_s2, step_s, n),
        ),
    }


def bound_ratios(
    run: Mapping[str, np.ndarray],
    gyro_noise_std_rad_s: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mu: float,
) -> dict[str, np.ndarray]:
    """Each of a run's errors divided by its growth bound, at every sample after t = 0. The run
    passes where every ratio is at most `BOUND_FACTOR`.

    Args:
        run: one run, as `read_run` returns it.
        gyro_noise_std_rad_s: rad/s, the gyro's per-sample 1-sigma noise.
        accel_noise_std_m_s2: m/s^2, the accelerometer's per-sample 1-sigma noise.
        step_s: s, the flight software's step.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        `{metric: (N - 1,) array}`, dimensionless, keyed as `error_growth` keys them.
    """
    growths = error_growth(run, gyro_noise_std_rad_s, accel_noise_std_m_s2, step_s, mu)
    return {name: error[1:] / bound[1:] for name, (error, bound) in growths.items()}


def violations(
    run: Mapping[str, np.ndarray],
    gyro_noise_std_rad_s: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mu: float,
) -> list[str]:
    """Every way a run fails the criterion, one message per metric.

    Args:
        run: one run, as `read_run` returns it.
        gyro_noise_std_rad_s: rad/s, the gyro's per-sample 1-sigma noise.
        accel_noise_std_m_s2: m/s^2, the accelerometer's per-sample 1-sigma noise.
        step_s: s, the flight software's step.
        mu: m^3/s^2, the central body's gravitational parameter.

    Returns:
        A message for each metric whose error is above `ERROR_AT_START` at t = 0, or above
        `BOUND_FACTOR` times its bound at a later sample, naming the earliest such sample. Empty
        when the run passes.
    """
    t = run["t_s"]
    found = []
    growths = error_growth(run, gyro_noise_std_rad_s, accel_noise_std_m_s2, step_s, mu)
    for name, (error, bound) in growths.items():
        if error[0] > ERROR_AT_START:
            found.append(f"{name} at t = 0 is {error[0]}, above {ERROR_AT_START}")
            continue
        over = np.flatnonzero(error[1:] > BOUND_FACTOR * bound[1:]) + 1
        if over.size:
            k = over[0]
            found.append(
                f"{name} exceeds {BOUND_FACTOR} x its bound from t = {t[k]} s: "
                f"{error[k]} > {BOUND_FACTOR * bound[k]}"
            )
    return found
