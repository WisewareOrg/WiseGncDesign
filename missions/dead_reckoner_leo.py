# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation
#   kernelspec:
#     display_name: WiseGncDesign
#     language: python
#     name: wise-gnc-design
# ---

# %% [markdown]
# # Mission: the dead reckoner in low Earth orbit
#
# The IMU dead reckoner on the IMU spacecraft, flown through the 500 km and 400 km scenarios and
# judged on the attitude ladder and the velocity and position rungs. The FSW brings its own
# capability claims; this mission chooses the vehicle, the rungs and the scenarios. Pick a session
# with `just session <name>`, run the `%%monte_carlo` cell, then `just judge`.

# %%
"""Mission: the IMU dead reckoner in low Earth orbit."""

from gnc_algorithms.imu_dead_reckoning import dead_reckoner
from mission import Mission, mission_tests

# %load_ext wise_dynamics.notebook

MISSION = Mission(
    name="dead_reckoner_leo",
    vehicle="imu_spacecraft",
    fsw=dead_reckoner,
    rungs=("SRS001", "SRS002", "SRS003", "SRS004", "SRS005"),
    scenarios=("TST001", "TST002"),
)

# %%
# %%monte_carlo
globals().update(mission_tests(MISSION))
