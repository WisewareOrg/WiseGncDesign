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
# `fprime_dead_reckoner` boots the deployment idle on the scenario's vehicle. The scenario's
# ground procedure gives the dead reckoner its state by command, as it gives the Python one.


# %%
@provides("SYS001")
def fprime_dead_reckoner(scenario: Scenario) -> FprimeModule:
    """The F´ dead reckoner, booted idle on a scenario's vehicle.

    Args:
        scenario: the scenario whose vehicle and `mu` the deployment takes.

    Returns:
        The `FprimeModule` running it.
    """
    return FprimeModule(
        scenario.vehicle.readers()["imu"],
        mu=scenario.mu_m3_s2["earth"],
        dcm_PB=np.asarray(scenario.vehicle.imu.dcm_PB),
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
#     q, r = "nav.bodyEciAttitude", "nav.bodyEciPos"
#     attitude = attitude_error_rad(p[f"tlm/{q}"][0], f[f"tlm/{q}"][0])
#     position = position_error_m(p[f"tlm/{r}"][0], f[f"tlm/{r}"][0])
#     axes[0].semilogy(p[f"tlm_t/{q}"][0], attitude, color="C0")
#     axes[1].semilogy(p[f"tlm_t/{r}"][0], position, color="C1")
# axes[0].set_ylabel("F´ vs Python attitude (rad)")
# axes[1].set_ylabel("F´ vs Python position (m)")
# axes[-1].set_xlabel("t (s)")
