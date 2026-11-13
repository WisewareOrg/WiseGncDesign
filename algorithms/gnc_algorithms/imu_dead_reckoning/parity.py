# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation,-kernelspec
# ---

# %% [markdown]
# # The dead reckoner's two builds, held to parity
#
# The IMU dead reckoner flown twice through the 500 km and 400 km scenarios on the IMU spacecraft:
# the algorithm notebook's Python estimator hosted by `gnc_cdh.basilisk`, and its F´ build, the
# WiseFsw deployment, run inside the simulation by `gnc_cdh.fprime`. Both claim the same capability
# and pass the same gross check. Case `k` flies the same dispersions and sensor noise in both, so
# the two builds are held to parity case by case. Build the deployment with `just fsw` first.

# %%
"""The dead reckoner's two builds, held to parity."""

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
# ## The two builds agree
#
# The cells below run in the notebook only: the judged rungs, then the builds' parity. Case for
# case, the builds write the same datasets, with the same dtypes, units and write times, and the
# same command log. Every value is equal but the estimate's, which agrees to `TOLERANCE`: position
# and velocity relative to the vector's norm, attitude as the principal angle between the two. A
# disagreement fails the cell, and with it the notebook's test.


# %% active="ipynb"
# from harness.notebook import judge
#
# judge()

# %% active="ipynb"
# from test_attitude_knowledge import attitude_error_rad
# from wise_dynamics.notebook import load_runs
#
# TOLERANCE = 1e-12
# vectors = ("tlm/nav.bodyEciPos", "tlm/nav.bodyEciVel")
# attitude = "tlm/nav.bodyEciAttitude"
# for scenario in ("leo500", "leo400"):
#     python = load_runs(f"Test_imu_spacecraft::test_dead_reckoner_{scenario}")
#     fprime = load_runs(f"Test_imu_spacecraft::test_fprime_dead_reckoner_{scenario}")
#     assert python, scenario
#     for p, f in zip(python, fprime, strict=True):
#         case = f"{scenario} case {p['attrs']['case']}"
#         assert p["attrs"]["case"] == f["attrs"]["case"], case
#         assert p["attrs"]["commands"] == f["attrs"]["commands"], case
#         p, f = p["datasets"], f["datasets"]
#         assert sorted(p) == sorted(f), case
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
