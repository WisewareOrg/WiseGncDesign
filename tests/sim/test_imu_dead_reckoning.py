"""The dead reckoner, hosted by `gnc_cdh.basilisk` on WiseDynamics' IMU spacecraft. Each case
runs one dispersed spacecraft, writes its run file, and holds its estimate within bounds derived
from its own drawn IMU biases."""

from importlib.metadata import version
from typing import Any

import numpy as np
from wise_dynamics.basilisk import RecordedField, run_case

from gnc_analysis.error_bounds import BOUND_FACTOR, ERROR_AT_START, error_growth
from gnc_analysis.runs import DATASETS, Run, load_run
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


def assert_within_bias_growth(run: Run, config: Any, mu: float) -> None:
    """Holds each error under `ERROR_AT_START` at t = 0, and under `BOUND_FACTOR` times its
    `error_growth` at every later sample, with the noise and step of the plant's `config`."""
    t = run.t_s
    growths = error_growth(
        run, config.gyro_noise_std_rad_s, config.accel_noise_std_m_s2, config.step_s, mu
    )
    for name, (error, growth) in growths.items():
        assert error[0] <= ERROR_AT_START, f"{name} at t = 0 is {error[0]}"
        over = np.flatnonzero(error[1:] > BOUND_FACTOR * growth[1:]) + 1
        assert over.size == 0, (
            f"{name} first exceeds {BOUND_FACTOR} x its derived growth at t = {t[over[0]]} s: "
            f"{error[over[0]]} > {BOUND_FACTOR * growth[over[0]]}"
        )


def test_imu_dead_reckoning_case(sim_plant, sim_duration_s, sim_run_writer, record_property):
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
    assert_within_bias_growth(run, sim_plant.config, sim_plant.mu)
