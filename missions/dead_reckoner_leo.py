# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation,-kernelspec
# ---

# %% [markdown]
# # Missions: the dead reckoner in low Earth orbit, on each vehicle
#
# The IMU dead reckoner flown through the 500 km and 400 km scenarios on the IMU spacecraft and on
# the heavy stand-in, and judged on the attitude ladder and the velocity and position rungs. The FSW
# brings its own capability claims; each mission chooses the vehicle, the rungs and the scenarios.
# Pick a session with `just session <name>`, run the `%%monte_carlo` cell, then `just judge`.

# %%
"""Missions: the IMU dead reckoner in low Earth orbit, on each vehicle."""

from algorithms.imu_dead_reckoning import dead_reckoner, parameters
from harness.mission import Mission, mission_tests

# %load_ext wise_dynamics.notebook

BASE = Mission(
    vehicle="imu_spacecraft",
    fsw=dead_reckoner,
    parameters=parameters,
    rungs=("SRS001", "SRS002", "SRS003", "SRS004", "SRS005"),
    scenarios=("TST001", "TST002"),
)
MISSIONS = [BASE, BASE.but(vehicle="heavy_imu_spacecraft")]

# %%
# %%monte_carlo
globals().update(mission_tests(*MISSIONS))


# %% active="ipynb"
# from harness.notebook import judge, plots
#
# judge()

# %% active="ipynb"
# plots("SRS001")

# %% active="ipynb"
# from wise_dynamics.notebook import load_runs
#
# runs = load_runs(Test_heavy_imu_spacecraft.test_dead_reckoner_leo500)
# len(runs), runs[0]["datasets"]["truth/q_BN"][0].shape
