"""The dead reckoner, hosted by `gnc_cdh.basilisk` on WiseDynamics' IMU spacecraft. Each case
runs one dispersed spacecraft, writes its run file, and holds its estimate within bounds derived
from its own drawn IMU biases."""

from importlib.metadata import version
from typing import Any

import numpy as np
from wise_dynamics.basilisk import RecordedField, run_case

from gnc_analysis.navigation_error import attitude_error_deg, position_error_m, velocity_error_m_s
from gnc_analysis.runs import DATASETS, Run, load_run
from gnc_cdh.basilisk import AlgorithmModule, make_fsw

IMU_DCM_PB = np.eye(3)
"""The flight software's mounting [PB] of the IMU: identity on this spacecraft."""

ERROR_AT_START = 1e-9
"""Bound on every error at t = 0 (rad, m, m/s), where the estimate starts from truth."""

BOUND_FACTOR = 3.0
"""Margin on each derived error growth, covering the terms the derivation leaves out."""


def estimate_fields(fsw: AlgorithmModule) -> dict[str, RecordedField]:
    """The estimate's run-file datasets, `est/<state field>`, read from the module's output
    maps, in the units the loader requires."""
    return {
        f"est/{m.state_field}": RecordedField(
            m.output, m.payload_field, DATASETS[f"est/{m.state_field}"].units
        )
        for m in fsw.output_maps
    }


def error_growth(run: Run, config: Any, mu: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each error of `run` at every sample, beside its growth derived from the run's drawn IMU
    biases `b_g`, `b_a` (`draw_gyro_bias_P`, `draw_accel_bias_P`), the plant's per-sample noise
    `sigma_g`, `sigma_a`, the IMU step `dt`, and the run's own mean motion `n = sqrt(mu / |r0|^3)`.

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
    """
    t = run.t_s
    dt = config.step_s
    b_g = float(np.linalg.norm(run.draws["gyro_bias_P"]))
    b_a = float(np.linalg.norm(run.draws["accel_bias_P"]))
    omega_dot = np.linalg.norm(np.diff(run.truth.omega_BN_B, axis=0), axis=1) / np.diff(t)
    n = np.sqrt(mu / float(np.linalg.norm(run.truth.r_N[0])) ** 3)
    sigma_g, sigma_a = config.gyro_noise_std_rad_s, config.accel_noise_std_m_s2
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


def assert_within_bias_growth(run: Run, config: Any, mu: float) -> None:
    """Holds each error under `ERROR_AT_START` at t = 0, and under `BOUND_FACTOR` times its
    `error_growth` at every later sample."""
    t = run.t_s
    for name, (error, growth) in error_growth(run, config, mu).items():
        assert error[0] <= ERROR_AT_START, f"{name} at t = 0 is {error[0]}"
        over = np.flatnonzero(error[1:] > BOUND_FACTOR * growth[1:]) + 1
        assert over.size == 0, (
            f"{name} first exceeds {BOUND_FACTOR} x its derived growth at t = {t[over[0]]} s: "
            f"{error[over[0]]} > {BOUND_FACTOR * growth[over[0]]}"
        )


def test_imu_dead_reckoning_case(sim_campaign, sim_plant, sim_run_writer, record_property):
    fsw = make_fsw(
        "imu_dead_reckoning",
        inputs=sim_plant.readers(),
        initial_state=sim_plant.initial_state,
        mountings={"imu": IMU_DCM_PB},
        mu=sim_plant.mu,
    )
    recording = run_case(
        sim_plant, fsw, fsw_outputs=fsw.output_messages, duration_s=sim_campaign.duration_s
    )
    datasets = recording.datasets({**sim_plant.recorded_fields, **estimate_fields(fsw)})
    distribution_version = version("wise-gnc-design")

    path = sim_run_writer(datasets, extra_attrs={"versions_wise_gnc_design": distribution_version})
    record_property("run_file", str(path))
    run = load_run(path)

    assert run.versions["wise_gnc_design"] == distribution_version
    assert_within_bias_growth(run, sim_plant.config, sim_plant.mu)
