from collections.abc import Callable
from pathlib import Path

import pytest
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from gnc_algorithms.imu_dead_reckoning import dead_reckoner, estimate_fields


def _case(sim_scenario: Leo500, sim_duration_s: float, sim_run_file: Callable[..., Path]) -> None:
    fsw = dead_reckoner(sim_scenario)
    sim_run_file(sim_scenario.run(fsw, estimate_fields(fsw), duration_s=sim_duration_s))


@pytest.mark.sim_runs(4)
@pytest.mark.sim_duration_s(300)
@pytest.mark.verifies("SRS001", "SRS002")
def test_loop_a(sim_scenario, sim_duration_s, sim_run_file):
    _case(sim_scenario, sim_duration_s, sim_run_file)


@pytest.mark.sim_runs(4)
@pytest.mark.sim_duration_s(300)
@pytest.mark.verifies("SRS002")
def test_loop_b(sim_scenario, sim_duration_s, sim_run_file):
    _case(sim_scenario, sim_duration_s, sim_run_file)
