"""The dead reckoner, hosted by `gnc_cdh.basilisk` on WiseDynamics' IMU spacecraft. Each case
runs one dispersed spacecraft, writes its run file, and holds its estimate within bounds derived
from its own drawn IMU biases."""

from importlib.metadata import version

import numpy as np
from wise_dynamics.basilisk import ImuSpacecraft, ImuSpacecraftConfig, RecordedField, run_case

from gnc_analysis.error_bounds import violations
from gnc_analysis.runs import DATASETS, load_run
from gnc_cdh.basilisk import AlgorithmModule, make_fsw

IMU_DCM_PB = np.eye(3)
"""The flight software's mounting [PB] of the IMU: identity on this spacecraft."""


def estimate_fields(fsw: AlgorithmModule) -> dict[str, RecordedField]:
    """The estimate's run-file datasets, `est/<state field>`, read from the module's output
    maps, in the units the loader requires."""
    return {
        f"est/{m.state_field}": RecordedField(
            m.output, m.payload_field, DATASETS[f"est/{m.state_field}"].units
        )
        for m in fsw.output_maps
    }


def bound_inputs() -> dict[str, float]:
    """The plant inputs of the accuracy bound, for this scenario and the campaign notebook
    alike: per-sample gyro and accelerometer noise and the IMU step from the nominal
    `ImuSpacecraftConfig`, and the central body's gravitational parameter (m^3/s^2) from
    `ImuSpacecraft.mu`, all read without building a plant. The campaign disperses initial state
    and biases only, so these are every case's values."""
    config = ImuSpacecraftConfig()
    return {
        "gyro_noise_std_rad_s": config.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": config.accel_noise_std_m_s2,
        "step_s": config.step_s,
        "mu": ImuSpacecraft.mu,
    }


def test_imu_dead_reckoning_case(sim_plant, sim_duration_s, sim_run_writer, record_property):
    inputs = bound_inputs()
    plant_inputs = {
        "gyro_noise_std_rad_s": sim_plant.config.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": sim_plant.config.accel_noise_std_m_s2,
        "step_s": sim_plant.config.step_s,
        "mu": sim_plant.mu,
    }
    assert plant_inputs == inputs, "the case's plant differs from the bound's inputs"

    fsw = make_fsw(
        "imu_dead_reckoning",
        inputs=sim_plant.readers(),
        initial_state=sim_plant.initial_state,
        mountings={"imu": IMU_DCM_PB},
        mu=sim_plant.mu,
    )
    recording = run_case(sim_plant, fsw, fsw_outputs=fsw.output_messages, duration_s=sim_duration_s)
    datasets = recording.datasets({**sim_plant.recorded_fields, **estimate_fields(fsw)})
    distribution_version = version("wise-gnc-design")

    path = sim_run_writer(datasets, extra_attrs={"versions_wise_gnc_design": distribution_version})
    record_property("run_file", str(path))
    run = load_run(path)

    assert run.versions["wise_gnc_design"] == distribution_version
    assert violations(run, **inputs) == []
