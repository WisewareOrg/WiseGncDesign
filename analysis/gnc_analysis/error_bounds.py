"""Accuracy bounds for a strapdown IMU dead-reckoning estimate: each error's growth derived from
a run's drawn IMU biases, its sensor noise and its orbit, and the ratio of each error to it.

A run is one run file read by `read_run`: dataset path to array (`t_s`, `truth/*`, `est/*`) and
root attribute name to value (`draw_*`)."""

from collections.abc import Mapping
from pathlib import Path

import h5py
import numpy as np

__all__ = [
    "BOUND_FACTOR",
    "ERROR_AT_START",
    "attitude_error_rad",
    "bound_ratios",
    "error_growth",
    "read_run",
    "violations",
]

ERROR_AT_START = 1e-9
"""Bound on every error at t = 0 (rad, m, m/s), where the estimate starts from truth."""

BOUND_FACTOR = 3.0
"""Margin on each derived error growth, covering the terms the derivation leaves out."""


def read_run(path: str | Path) -> dict[str, np.ndarray]:
    """Every dataset of the run file at `path` by its path, and every root attribute by name."""
    with h5py.File(path, "r") as f:
        run = {name: np.asarray(value) for name, value in f.attrs.items()}
        for group in f.values():
            for name, dataset in group.items() if isinstance(group, h5py.Group) else ():
                run[f"{group.name[1:]}/{name}"] = dataset[()]
        run["t_s"] = f["t_s"][()]
    return run


def _quaternion(sigma: np.ndarray) -> np.ndarray:
    s2 = np.sum(sigma * sigma, axis=-1, keepdims=True)
    return np.concatenate((1.0 - s2, 2.0 * sigma), axis=-1) / (1.0 + s2)


def attitude_error_rad(run: Mapping[str, np.ndarray]) -> np.ndarray:
    """(N,) rad, the principal angle between `truth/sigma_BN` and `est/sigma_BN` at each sample,
    from their quaternions' relative rotation."""
    q1, q2 = _quaternion(run["truth/sigma_BN"]), _quaternion(run["est/sigma_BN"])
    scalar = np.sum(q1 * q2, axis=-1)
    vector = q2[:, :1] * q1[:, 1:] - q1[:, :1] * q2[:, 1:] - np.cross(q1[:, 1:], q2[:, 1:])
    return 2.0 * np.arctan2(np.linalg.norm(vector, axis=-1), np.abs(scalar))


def error_growth(
    run: Mapping[str, np.ndarray],
    gyro_noise_std_rad_s: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mu: float,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each error of `run` at every sample, beside its growth derived from the run's drawn IMU
    biases `b_g`, `b_a` (`draw_gyro_bias_P_rad_s`, `draw_accel_bias_P_m_s2`), the per-sample noise
    `sigma_g`, `sigma_a` of the IMU that produced it, the flight software's step `dt`, and the
    run's own mean motion `n = sqrt(mu / |r0|^3)`.

    Attitude, rad: `|b_g| t + 1/2 max|omega_dot| dt t + 3 sigma_g sqrt(t dt)`.
    - A constant gyro bias turns the estimate at most `|b_g|` faster than truth.
    - The integrator holds each sampled rate over its step while the true rate changes by up to
      `max|omega_dot| dt`, which leaves at most half that per second. `max|omega_dot|` is the
      largest finite difference of the run's own `truth/omega_BN_B`.
    - The gyro's white noise is a random walk of `sigma_g sqrt(t dt)` per axis, taken at 3 sigma.

    Velocity, m/s: `(1 + (n t)^2 / 3) (|b_a| t + 3 sigma_a sqrt(t dt))`.
    - A constant accelerometer bias adds `|b_a| t`; its white noise is a random walk of
      `sigma_a sqrt(t dt)`, taken at 3 sigma.
    - Gravity is evaluated at the estimated position, so the position error feeds back through
      the gravity gradient `G = (mu / r^3)(3 r_hat r_hat^T - I)`, whose eigenvalues are `2 n^2`,
      `-n^2` and `-n^2`. The factor `1 + (n t)^2 / 3` is that feedback to first order: the
      first Picard iterate of `dv/dt = G dr + f` with `|G| <= 2 n^2`. The linearized worst case
      over any bias-direction history is within 1.03 times it, verified to 4 orbits. It
      multiplies the noise term as well, which feeds back the same way.

    Position, m: `(1 + (n t)^2 / 6) (|b_a| t^2 / 2 + 3 sigma_a sqrt(dt / 3) t^(3/2))`.
    - A constant accelerometer bias gives `|b_a| t^2 / 2` before feedback; the accelerometer
      random walk integrates to `sigma_a sqrt(dt / 3) t^(3/2)`, taken at 3 sigma.
    - The factor `1 + (n t)^2 / 6` is the gravity-gradient feedback to first order, the first
      Picard iterate of the same equation. Without it the Clohessy-Wiltshire along-track
      secular growth reaches 3.29 times `|b_a| t^2 / 2` for the worst bias-direction history;
      the linearized worst case is within 1.002 times the factored form, verified to 4 orbits.

    The linearization holds to 4 orbits, where the position error stays within about 6% of the
    orbit radius at the largest drawn bias. With every sensor error zero, velocity and position
    errors stay under 5e-11 m/s and 4e-8 m over an orbit, so the held specific force needs no
    term. `BOUND_FACTOR` covers what the leading terms omit, chiefly the attitude error rotating
    the accelerometer bias, which is second order and under 15% of the bias term.

    Args:
        run: the run, carrying `draw_gyro_bias_P_rad_s` and `draw_accel_bias_P_m_s2`.
        gyro_noise_std_rad_s: per-sample 1-sigma gyro noise, rad/s.
        accel_noise_std_m_s2: per-sample 1-sigma accelerometer noise, m/s^2.
        step_s: the flight software's step `dt`, the interval between the samples it reads, s.
        mu: gravitational parameter of the central body, m^3/s^2.

    Returns:
        `{metric: (error, growth)}` for `"attitude error [rad]"`, `"velocity error [m/s]"` and
        `"position error [m]"`, each a pair of (N,) arrays over `t_s`.
    """
    t = run["t_s"]
    dt = step_s
    b_g = float(np.linalg.norm(run["draw_gyro_bias_P_rad_s"]))
    b_a = float(np.linalg.norm(run["draw_accel_bias_P_m_s2"]))
    omega_dot = np.linalg.norm(np.diff(run["truth/omega_BN_B"], axis=0), axis=1) / np.diff(t)
    n = np.sqrt(mu / float(np.linalg.norm(run["truth/r_N"][0])) ** 3)
    sigma_g, sigma_a = gyro_noise_std_rad_s, accel_noise_std_m_s2
    return {
        "attitude error [rad]": (
            attitude_error_rad(run),
            b_g * t + 0.5 * omega_dot.max() * dt * t + 3.0 * sigma_g * np.sqrt(t * dt),
        ),
        "velocity error [m/s]": (
            np.linalg.norm(run["truth/v_N"] - run["est/v_N"], axis=-1),
            (1.0 + (n * t) ** 2 / 3.0) * (b_a * t + 3.0 * sigma_a * np.sqrt(t * dt)),
        ),
        "position error [m]": (
            np.linalg.norm(run["truth/r_N"] - run["est/r_N"], axis=-1),
            (1.0 + (n * t) ** 2 / 6.0)
            * (0.5 * b_a * t**2 + 3.0 * sigma_a * np.sqrt(dt / 3.0) * t**1.5),
        ),
    }


def bound_ratios(
    run: Mapping[str, np.ndarray],
    gyro_noise_std_rad_s: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mu: float,
) -> dict[str, np.ndarray]:
    """Each error of `run` divided by its `error_growth`, at every sample after t = 0, as
    `{metric: (N - 1,) array}`. A run stays within its bound where every ratio is at most
    `BOUND_FACTOR`."""
    growths = error_growth(run, gyro_noise_std_rad_s, accel_noise_std_m_s2, step_s, mu)
    return {name: error[1:] / growth[1:] for name, (error, growth) in growths.items()}


def violations(
    run: Mapping[str, np.ndarray],
    gyro_noise_std_rad_s: float,
    accel_noise_std_m_s2: float,
    step_s: float,
    mu: float,
) -> list[str]:
    """Every way `run` leaves its bound, one message per metric: an error above
    `ERROR_AT_START` at t = 0, or above `BOUND_FACTOR` times its `error_growth` at a later
    sample, naming the earliest such sample. Empty when the run stays within its bound."""
    t = run["t_s"]
    found = []
    growths = error_growth(run, gyro_noise_std_rad_s, accel_noise_std_m_s2, step_s, mu)
    for name, (error, growth) in growths.items():
        if error[0] > ERROR_AT_START:
            found.append(f"{name} at t = 0 is {error[0]}, above {ERROR_AT_START}")
            continue
        over = np.flatnonzero(error[1:] > BOUND_FACTOR * growth[1:]) + 1
        if over.size:
            k = over[0]
            found.append(
                f"{name} exceeds {BOUND_FACTOR} x its derived growth from t = {t[k]} s: "
                f"{error[k]} > {BOUND_FACTOR * growth[k]}"
            )
    return found
