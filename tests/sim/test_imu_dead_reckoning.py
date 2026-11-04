"""The dead reckoner at 1 Hz on WiseDynamics' IMU spacecraft in Leo500.

`gnc_cdh.basilisk` hosts it, and the dynamics step at `--sim-fidelity`'s rate. Each case runs one
dispersed spacecraft, writes its run file, and holds its estimate within bounds derived from its
own drawn IMU biases.
"""

from importlib.metadata import version
from typing import Any

import numpy as np
from Basilisk.architecture import messaging
from wise_dynamics.basilisk import ImuSpacecraft, Leo500

from gnc_analysis.error_bounds import read_run, violations
from gnc_cdh.basilisk import BINDINGS, AlgorithmModule, make_fsw

IMU_DCM_PB = np.eye(3)
"""The flight software's mounting [PB] of the IMU: identity on this spacecraft."""

UNITS = {"sigma_BN": "MRP", "r_N": "m", "v_N": "m/s"}
"""The units of each estimate field in the run file."""


def estimate_fields(fsw: AlgorithmModule) -> dict[str, tuple[Any, str, str]]:
    """The estimate's run-file datasets, `est/<state field>`, by the dead reckoner's binding.

    Takes the host module `fsw`; returns each dataset path to `(message, field, units)`.
    """
    return {
        f"est/{state_field}": (fsw.output_messages[message], message_field, UNITS[state_field])
        for state_field, (message, message_field) in BINDINGS["imu_dead_reckoning"].outputs.items()
    }


def bound_inputs() -> dict[str, float]:
    """The bound's inputs, for this test and the Monte Carlo notebook alike.

    Returns the IMU noise from `ImuSpacecraft` (rad/s and m/s^2), the flight software's step
    `AlgorithmModule.period_s` (s), and Earth's mu from `Leo500` (m^3/s^2).
    """
    return {
        "gyro_noise_std_rad_s": ImuSpacecraft.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": ImuSpacecraft.accel_noise_std_m_s2,
        "step_s": AlgorithmModule.period_s,
        "mu": Leo500.mu_m3_s2["earth"],
    }


def dead_reckoner(scenario: Leo500) -> AlgorithmModule:
    """The dead reckoner's host module on `scenario`'s vehicle."""
    return make_fsw(
        "imu_dead_reckoning",
        inputs=scenario.vehicle.readers(),
        initial_state=scenario.initial_state,
        dcm_PB=IMU_DCM_PB,
        mu=Leo500.mu_m3_s2["earth"],
    )


def test_the_estimate_is_written_at_whole_seconds():
    """Run 3.5 s in Leo500, the estimate is last written at 3 s.

    The module runs at its 1 s `period_s`, not at the dynamics step.
    """
    scenario = Leo500()
    fsw = dead_reckoner(scenario)
    estimate = messaging.NavAttMsgReader()
    estimate.subscribeTo(fsw.output_messages["nav_att"])

    scenario.run(fsw, {}, duration_s=3.5)

    assert estimate.timeWritten() == 3_000_000_000
    assert fsw.algorithm.t == 3.0


def test_imu_dead_reckoning_case(sim_scenario, sim_duration_s, sim_run_file):
    """One Monte Carlo case holds every error within its bound.

    The dead reckoner flies `sim_scenario` for `sim_duration_s` (s), and `sim_run_file` writes the
    run file the bound reads.
    """
    fsw = dead_reckoner(sim_scenario)
    datasets = sim_scenario.run(fsw, estimate_fields(fsw), duration_s=sim_duration_s)
    path = sim_run_file(datasets, {"versions_wise_gnc_design": version("wise-gnc-design")})

    assert violations(read_run(path), **bound_inputs()) == []
