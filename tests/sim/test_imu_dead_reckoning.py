"""The dead reckoner, hosted by `gnc_cdh.basilisk` at 1 Hz on WiseDynamics' IMU spacecraft in its
LEO scenario, whose dynamics step at 50 Hz. Each case runs one dispersed spacecraft, writes its run
file, and holds its estimate within bounds derived from its own drawn IMU biases."""

from importlib.metadata import version
from typing import Any

import numpy as np
from wise_dynamics.basilisk import ImuSpacecraft, Leo500

from gnc_analysis.error_bounds import violations
from gnc_analysis.runs import DATASETS, load_run
from gnc_cdh.basilisk import PERIOD_S, AlgorithmModule, make_fsw

IMU_DCM_PB = np.eye(3)
"""The flight software's mounting [PB] of the IMU: identity on this spacecraft."""


def estimate_fields(fsw: AlgorithmModule) -> dict[str, tuple[Any, str, str]]:
    """The estimate's run-file datasets, `est/<state field>`, as `(message, field, units)` read
    from the module's output maps, in the units the loader requires."""
    return {
        f"est/{m.state_field}": (
            fsw.output_messages[m.output],
            m.payload_field,
            DATASETS[f"est/{m.state_field}"].units,
        )
        for m in fsw.output_maps
    }


def bound_inputs() -> dict[str, float]:
    """The simulation inputs of the accuracy bound, for this scenario and the Monte Carlo notebook
    alike: per-sample gyro and accelerometer noise from the `ImuSpacecraft` class attributes, the
    flight software's step from `PERIOD_S`, and Earth's gravitational parameter (m^3/s^2) from
    `Leo500.mu_m3_s2`, all read without building anything. A Monte Carlo run disperses initial
    attitude, body rate and biases only, so these are every case's values."""
    return {
        "gyro_noise_std_rad_s": ImuSpacecraft.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": ImuSpacecraft.accel_noise_std_m_s2,
        "step_s": PERIOD_S,
        "mu": Leo500.mu_m3_s2["earth"],
    }


def test_imu_dead_reckoning_case(sim_scenario, sim_duration_s, sim_run_file, record_property):
    vehicle = sim_scenario.vehicle
    inputs = bound_inputs()
    case_inputs = {
        "gyro_noise_std_rad_s": vehicle.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": vehicle.accel_noise_std_m_s2,
        "step_s": PERIOD_S,
        "mu": sim_scenario.mu_m3_s2["earth"],
    }
    assert case_inputs == inputs, "the case's vehicle or scenario differs from the bound's inputs"

    fsw = make_fsw(
        "imu_dead_reckoning",
        inputs=vehicle.readers(),
        initial_state=sim_scenario.initial_state,
        mountings={"imu": IMU_DCM_PB},
        mu=sim_scenario.mu_m3_s2["earth"],
    )
    datasets = sim_scenario.run(fsw, estimate_fields(fsw), duration_s=sim_duration_s)
    distribution_version = version("wise-gnc-design")

    path = sim_run_file(datasets, {"versions_wise_gnc_design": distribution_version})
    record_property("run_file", str(path))
    run = load_run(path)

    assert run.versions["wise_gnc_design"] == distribution_version
    assert violations(run, **inputs) == []
