"""The dead reckoner, hosted by `gnc_cdh.basilisk` at 1 Hz on WiseDynamics' IMU spacecraft in
Leo500, whose dynamics step at 50 Hz. Each case runs one dispersed spacecraft, writes its run file,
and holds its estimate within bounds derived from its own drawn IMU biases."""

from importlib.metadata import version
from typing import Any

import numpy as np
from wise_dynamics.basilisk import ImuSpacecraft, Leo500

from gnc_analysis.error_bounds import read_run, violations
from gnc_cdh.basilisk import PERIOD_S, AlgorithmModule, make_fsw

IMU_DCM_PB = np.eye(3)
"""The flight software's mounting [PB] of the IMU: identity on this spacecraft."""

UNITS = {"sigma_BN": "MRP", "r_N": "m", "v_N": "m/s"}
"""The units of each estimate field in the run file."""


def estimate_fields(fsw: AlgorithmModule) -> dict[str, tuple[Any, str, str]]:
    """The estimate's run-file datasets, `est/<state field>`, as `(message, field, units)` read
    from the module's output maps."""
    return {
        f"est/{m.state_field}": (
            fsw.output_messages[m.output],
            m.payload_field,
            UNITS[m.state_field],
        )
        for m in fsw.output_maps
    }


def bound_inputs() -> dict[str, float]:
    """The bound's inputs, for this test and the Monte Carlo notebook alike: the IMU noise from
    `ImuSpacecraft`, the flight software's step `PERIOD_S`, and Earth's mu from `Leo500`."""
    return {
        "gyro_noise_std_rad_s": ImuSpacecraft.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": ImuSpacecraft.accel_noise_std_m_s2,
        "step_s": PERIOD_S,
        "mu": Leo500.mu_m3_s2["earth"],
    }


def test_imu_dead_reckoning_case(sim_scenario, sim_duration_s, sim_run_file):
    fsw = make_fsw(
        "imu_dead_reckoning",
        inputs=sim_scenario.vehicle.readers(),
        initial_state=sim_scenario.initial_state,
        mountings={"imu": IMU_DCM_PB},
        mu=Leo500.mu_m3_s2["earth"],
    )
    datasets = sim_scenario.run(fsw, estimate_fields(fsw), duration_s=sim_duration_s)
    path = sim_run_file(datasets, {"versions_wise_gnc_design": version("wise-gnc-design")})

    assert violations(read_run(path), **bound_inputs()) == []
