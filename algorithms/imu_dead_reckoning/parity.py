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
# The cells below run in the notebook only: the judged rungs, then the builds' parity. Case for
# case, the builds write the same datasets, with the same dtypes, units and write times, and the
# same command log; the F´ build also records its rate group's health, which is its own and not
# compared. Every value is equal but the estimate's, which agrees to `TOLERANCE`: position
# and velocity relative to the vector's norm, attitude as the principal angle between the two. A
# disagreement fails the cell, and with it the notebook's test.


# %% active="ipynb"
# from harness.notebook import judge
#
# judge()

# %% active="ipynb"
# import numpy as np
# from test_attitude_knowledge import attitude_error_rad
# from wise_dynamics.notebook import load_runs
#
# TOLERANCE = 1e-12
# vectors = ("tlm/nav.bodyEciPos", "tlm/nav.bodyEciVel")
# attitude = "tlm/nav.bodyEciAttitude"
# for scenario in ("leo500", "leo400"):
#     python = load_runs(f"Test_imu_spacecraft::test_ImuDeadReckoning_python_{scenario}")
#     fprime = load_runs(f"Test_imu_spacecraft::test_ImuDeadReckoning_fprime_{scenario}")
#     assert python, scenario
#     for p, f in zip(python, fprime, strict=True):
#         case = f"{scenario} case {p['attrs']['case']}"
#         assert p["attrs"]["case"] == f["attrs"]["case"], case
#         assert p["attrs"]["commands"] == f["attrs"]["commands"], case
#         p, f = p["datasets"], f["datasets"]
#         assert set(p) <= set(f), case
#         fprime_only = {name.split("/", 1)[1] for name in set(f) - set(p)}
#         assert not any(name.startswith("nav.") for name in fprime_only), case
#         assert {*vectors, attitude} <= set(p), case
#         for name, (values, units) in p.items():
#             assert values.dtype == f[name][0].dtype, f"{case} {name}"
#             assert units == f[name][1], f"{case} {name}"
#             if name not in (*vectors, attitude):
#                 np.testing.assert_array_equal(values, f[name][0], err_msg=f"{case} {name}")
#         for name in vectors:
#             error = np.linalg.norm(p[name][0] - f[name][0], axis=1)
#             worst = np.max(error / np.linalg.norm(p[name][0], axis=1))
#             assert worst <= TOLERANCE, f"{case} {name}: {worst:.1e} relative"
#         worst = np.max(attitude_error_rad(p[attitude][0], f[attitude][0]))
#         assert worst <= TOLERANCE, f"{case} {attitude}: {worst:.1e} rad"
