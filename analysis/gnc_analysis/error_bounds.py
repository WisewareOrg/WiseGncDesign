"""Accuracy bounds for a strapdown IMU dead-reckoning estimate: each error's growth derived from
a run's drawn IMU biases, its sensor noise and its orbit, and the ratio of each error to it."""

import numpy as np

from gnc_analysis.navigation_error import attitude_error_deg, position_error_m, velocity_error_m_s
from gnc_analysis.runs import Run

__all__ = ["BOUND_FACTOR", "ERROR_AT_START", "bound_ratios", "error_growth"]

ERROR_AT_START = 1e-9
"""Bound on every error at t = 0 (rad, m, m/s), where the estimate starts from truth."""

BOUND_FACTOR = 3.0
"""Margin on each derived error growth, covering the terms the derivation leaves out."""


def error_growth(
    run: Run, gyro_noise_std_rad_s: float, accel_noise_std_m_s2: float, step_s: float, mu: float
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each error of `run` at every sample, beside its growth derived from the run's drawn IMU
    biases `b_g`, `b_a` (`draw_gyro_bias_P`, `draw_accel_bias_P`), the per-sample noise
    `sigma_g`, `sigma_a` and IMU step `dt` of the plant that produced it, and the run's own mean
    motion `n = sqrt(mu / |r0|^3)`.

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
        run: the run, carrying `draw_gyro_bias_P` and `draw_accel_bias_P`.
        gyro_noise_std_rad_s: per-sample 1-sigma gyro noise, rad/s.
        accel_noise_std_m_s2: per-sample 1-sigma accelerometer noise, m/s^2.
        step_s: IMU sample interval `dt`, s.
        mu: gravitational parameter of the central body, m^3/s^2.

    Returns:
        `{metric: (error, growth)}` for `"attitude error [rad]"`, `"velocity error [m/s]"` and
        `"position error [m]"`, each a pair of (N,) arrays over `run.t_s`.
    """
    t = run.t_s
    dt = step_s
    b_g = float(np.linalg.norm(run.draws["gyro_bias_P"]))
    b_a = float(np.linalg.norm(run.draws["accel_bias_P"]))
    omega_dot = np.linalg.norm(np.diff(run.truth.omega_BN_B, axis=0), axis=1) / np.diff(t)
    n = np.sqrt(mu / float(np.linalg.norm(run.truth.r_N[0])) ** 3)
    sigma_g, sigma_a = gyro_noise_std_rad_s, accel_noise_std_m_s2
    return {
        "attitude error [rad]": (
            np.radians(attitude_error_deg(run)),
            b_g * t + 0.5 * omega_dot.max() * dt * t + 3.0 * sigma_g * np.sqrt(t * dt),
        ),
        "velocity error [m/s]": (
            velocity_error_m_s(run),
            (1.0 + (n * t) ** 2 / 3.0) * (b_a * t + 3.0 * sigma_a * np.sqrt(t * dt)),
        ),
        "position error [m]": (
            position_error_m(run),
            (1.0 + (n * t) ** 2 / 6.0)
            * (0.5 * b_a * t**2 + 3.0 * sigma_a * np.sqrt(dt / 3.0) * t**1.5),
        ),
    }


def bound_ratios(
    run: Run, gyro_noise_std_rad_s: float, accel_noise_std_m_s2: float, step_s: float, mu: float
) -> dict[str, np.ndarray]:
    """Each error of `run` divided by its `error_growth`, at every sample after t = 0, as
    `{metric: (N - 1,) array}`. A run stays within its bound where every ratio is at most
    `BOUND_FACTOR`."""
    growths = error_growth(run, gyro_noise_std_rad_s, accel_noise_std_m_s2, step_s, mu)
    return {name: error[1:] / growth[1:] for name, (error, growth) in growths.items()}
