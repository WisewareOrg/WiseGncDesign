# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation,-kernelspec
# ---

# %% [markdown]
# # Missions: the dead reckoner, Python and F´, in low Earth orbit
#
# The IMU dead reckoner flown twice through the 500 km and 400 km scenarios on the IMU spacecraft:
# the notebook's Python estimator hosted by `gnc_cdh.basilisk`, and its F´ build, the WiseFsw
# deployment, run inside the simulation by `gnc_cdh.fprime`. Both claim the same capability and pass
# the same gross check. Case `k` flies the same dispersions and sensor noise in both, so the two
# estimates compare case by case. Build the deployment with `just fsw` first.

# %%
"""Missions: the dead reckoner, Python and F´, in low Earth orbit."""

import numpy as np
from wise_dynamics.basilisk import Scenario

from gnc_algorithms.imu_dead_reckoning import dead_reckoner
from gnc_algorithms.imu_dead_reckoning.gross_check import gross_check
from gnc_cdh.fprime import FprimeModule
from harness.mission import Mission, mission_tests, provides

# %load_ext wise_dynamics.notebook


# %% [markdown]
# ## The F´ flight software
#
# `fprime_dead_reckoner` boots the deployment on the scenario's vehicle. Until the `initNavState`
# command exists, the dead reckoner's initial state is handed over at boot, as the Python one's is.


# %%
@provides("SYS001")
def fprime_dead_reckoner(scenario: Scenario) -> FprimeModule:
    """The F´ dead reckoner, booted at t = 0 from a scenario's initial state, on its vehicle.

    Args:
        scenario: the scenario whose vehicle, `mu` and initial state the deployment takes.

    Returns:
        The `FprimeModule` running it.
    """
    return FprimeModule(
        scenario.vehicle.readers()["imu"],
        mu=scenario.mu_m3_s2["earth"],
        dcm_PB=np.asarray(scenario.vehicle.imu.dcm_PB),
        initial=scenario.initial_state(),
    )


# %%
PYTHON = Mission(
    vehicle="imu_spacecraft",
    fsw=dead_reckoner,
    rungs=("SRS001", "SRS002", "SRS003", "SRS004", "SRS005"),
    scenarios=("TST001", "TST002"),
    check=gross_check,
)
MISSIONS = [PYTHON, PYTHON.but(fsw=fprime_dead_reckoner)]

# %%
# %%monte_carlo
globals().update(mission_tests(*MISSIONS))


# %% [markdown]
# ## The two builds, case by case
#
# The cells below run in the notebook only: the judged rungs, then, for every case, how far the F´
# estimate sits from the Python one over time.


# %% active="ipynb"
# import matplotlib.pyplot as plt
# from harness.notebook import judge
# from test_attitude_knowledge import attitude_error_rad
# from test_position_knowledge import position_error_m
# from wise_dynamics.notebook import load_runs
#
# judge()

# %% active="ipynb"
# python = load_runs(Test_imu_spacecraft.test_dead_reckoner_leo500)
# fprime = load_runs(Test_imu_spacecraft.test_fprime_dead_reckoner_leo500)
# figure, axes = plt.subplots(2, 1, sharex=True, figsize=(8, 6), layout="constrained")
# for p, f in zip(python, fprime, strict=True):
#     p, f = p["datasets"], f["datasets"]
#     t = p["t_s"][0]
#     attitude = attitude_error_rad(p["est/sigma_BN"][0], f["est/sigma_BN"][0])
#     position = position_error_m(p["est/r_BN_N"][0], f["est/r_BN_N"][0])
#     axes[0].semilogy(t, attitude, color="C0")
#     axes[1].semilogy(t, position, color="C1")
# axes[0].set_ylabel("F´ vs Python attitude (rad)")
# axes[1].set_ylabel("F´ vs Python position (m)")
# axes[-1].set_xlabel("t (s)")
