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


def assert_within_bias_growth(run: Run, config: Any) -> None:
    """Holds each error, at every sample, under `BOUND_FACTOR` times its growth derived from
    the run's drawn IMU biases, and under `ERROR_AT_START` at t = 0.

    Derivation, with the IMU sampled every `dt = config.step_s`:
    - A constant gyro bias `b_g` turns the estimate at most `|b_g|` faster than truth, so the
      attitude error angle grows at most `|b_g| t`. The gyro's white noise, `sigma_g` per sample,
      adds a random walk of `sigma_g sqrt(t dt)` per axis, taken at 3 sigma.
    - A constant accelerometer bias `b_a` and noise `sigma_a` bound the velocity error the same
      way: `|b_a| t + 3 sigma_a sqrt(t dt)`.
    - The velocity error integrates to a position error of `|b_a| t^2 / 2`. The noise term is
      negligible beside it.

    `BOUND_FACTOR` covers what these leading terms omit:
    - the RK4 step holds the rate constant over `dt` while the hub precesses;
    - gravity is evaluated at the estimated position, not the true one;
    - the attitude error rotates the accelerometer bias.
    """
    t = run.t_s
    dt = config.step_s
    b_g = float(np.linalg.norm(run.draws["gyro_bias_P"]))
    b_a = float(np.linalg.norm(run.draws["accel_bias_P"]))
    random_walk = 3.0 * np.sqrt(t * dt)
    errors = {
        "attitude error [rad]": (
            np.radians(attitude_error_deg(run)),
            b_g * t + config.gyro_noise_std_rad_s * random_walk,
        ),
        "velocity error [m/s]": (
            velocity_error_m_s(run),
            b_a * t + config.accel_noise_std_m_s2 * random_walk,
        ),
        "position error [m]": (position_error_m(run), 0.5 * b_a * t**2),
    }
    for name, (error, growth) in errors.items():
        assert error[0] <= ERROR_AT_START, f"{name} at t = 0 is {error[0]}"
        over = np.flatnonzero(error[1:] > BOUND_FACTOR * growth[1:]) + 1
        assert over.size == 0, (
            f"{name} first exceeds {BOUND_FACTOR} x its bias growth at t = {t[over[0]]} s: "
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
    assert_within_bias_growth(run, sim_plant.config)
