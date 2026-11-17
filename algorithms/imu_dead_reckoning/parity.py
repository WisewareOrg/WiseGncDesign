# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation,-kernelspec
# ---

# %% [markdown]
# # The dead reckoner's two builds, held to parity
#
# The IMU dead reckoner's configuration, `ImuDeadReckoning`, flown twice through the 500 km and
# 400 km scenarios on the IMU spacecraft: on the Python build, the algorithm notebook's estimator
# hosted by `fsw.python`, and on the F´ build, the WiseFsw deployment, run inside the simulation by
# `lab`. The F´ build boots the deployment idle, PrmDb loading the `.dat` F´'s tool makes from the
# case's record, and the scenario's ground procedure gives the dead reckoner its state by command,
# as it gives the Python one. Both builds fly the one configuration, so both claim its capability,
# and both pass the same gross check. Case `k` flies the same dispersions and sensor noise in both,
# so the two builds are held to parity case by case. Build the deployment with `just fsw` first.

# %%
"""The dead reckoner's two builds, held to parity."""

from algorithms.imu_dead_reckoning.gross_check import gross_check
from harness.mission import Mission, mission_tests

# %load_ext wise_dynamics.notebook


# %%
PYTHON = Mission(
    vehicle="imu_spacecraft",
    gnc="ImuDeadReckoning",
    build="python",
    rungs=("SRS001", "SRS002", "SRS003", "SRS004", "SRS005"),
    scenarios=("TST001", "TST002"),
    check=gross_check,
)
MISSIONS = [PYTHON, PYTHON.but(build="fprime")]

# %%
# %%monte_carlo
globals().update(mission_tests(*MISSIONS))


# %% [markdown]
# ## The two builds agree
#
# The cells below run in the notebook only: the judged rungs, then the builds' parity.
# `harness/parity.py` compares them case for case: the telemetry each GNC component declares and the
# log of commands sent to them, every value exact but floats, which agree to its `TOLERANCE`, each
# rule stated with its reason in that module. A disagreement fails the cell, and with it the
# notebook's test.


# %% active="ipynb"
# from harness.notebook import judge
#
# judge()

# %% active="ipynb"
# from harness.parity import session_parity
#
# assert session_parity() >= len(PYTHON.scenarios)
