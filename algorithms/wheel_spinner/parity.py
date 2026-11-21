# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation,-kernelspec
# ---

# %% [markdown]
# # The wheel spinner's two builds, held to parity
#
# The wheel spinner's configuration, `WheelSpinning`, flown twice through the `wheel_leo500`
# scenario on the wheel spacecraft: on the Python build, the algorithm notebook's spinner hosted by
# `fsw.python`, and on the F´ build, the WiseFsw deployment, run inside the simulation by `lab`. The
# F´ build boots the deployment on the `.dat` F´'s tool makes from the case's record, so both builds
# command the record's torque. Both builds fly the one configuration, so both claim its capability,
# and case `k` flies the same dispersions in both, so the two builds are held to parity case by
# case. Build the deployment with `just fsw` first.

# %%
"""The wheel spinner's two builds, held to parity."""

from harness.mission import Mission, mission_tests

# %load_ext wise_dynamics.notebook


# %%
PYTHON = Mission(
    vehicle="imu_wheel_spacecraft",
    gnc="WheelSpinning",
    build="python",
    rungs=("SRS006",),
    scenarios=("TST003",),
)
MISSIONS = [PYTHON, PYTHON.but(build="fprime")]

# %%
# %%monte_carlo
globals().update(mission_tests(*MISSIONS))


# %% [markdown]
# ## The two builds agree
#
# The cells below run in the notebook only: the judged rung, then, with the F´ build, the builds'
# parity. `harness/parity.py` compares this notebook's twins case for case, by the rules and reasons
# its module docstring states. A disagreement fails the cell, and with it the notebook's test.


# %% active="ipynb"
# from harness.notebook import judge
#
# judge()

# %% active="ipynb"
# from pathlib import Path
#
# from harness.parity import session_parity
# from lab import built
#
# if built(PYTHON.gnc):
#     assert session_parity(notebook=Path("parity.py")) == len(PYTHON.scenarios)
