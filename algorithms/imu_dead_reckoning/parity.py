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
# the algorithm notebook's Python estimator hosted by `fsw.python`, and its F´ build, the
# WiseFsw deployment, run inside the simulation by `lab`. Both claim the same capability
# and pass the same gross check. Case `k` flies the same dispersions and sensor noise in both, so
# the two builds are held to parity case by case. Build the deployment with `just fsw` first.

# %%
"""The dead reckoner's two builds, held to parity."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from wise_dynamics.basilisk import Scenario

from algorithms.imu_dead_reckoning import dead_reckoner, parameters
from algorithms.imu_dead_reckoning.gross_check import gross_check
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from harness.mission import Mission, mission_tests, provides
from lab import Adapter

# %load_ext wise_dynamics.notebook


# %% [markdown]
# ## The F´ flight software
#
# `fprime_dead_reckoner` boots the deployment idle on the scenario's vehicle, PrmDb loading the
# `.dat` F´'s tool makes from the case's record. The scenario's ground procedure gives the dead
# reckoner its state by command, as it gives the Python one. `FprimeBuild` pairs the two sides of
# the F´ build: the lab adapter that WiseDynamics' host ticks, and the ground station on its radio
# link.


# %%
class FprimeBuild:
    """The F´ build as the harness flies it: the lab adapter, and the ground station on it.

    `period_s`, `boot` and `tick` are the adapter's, which WiseDynamics' `FswHost` hosts; the
    radio edge, `dictionary`, `uplink`, `responses`, `telemetry` and `values`, is the station's.

    Attributes:
        period_s: s, the adapter's period.
        dictionary: the station's dictionary.
        build: the adapter's build identity.
    """

    period_s: float
    dictionary: Dictionary
    build: dict[str, str]

    def __init__(self, adapter: Adapter, station: FprimeStation) -> None:
        """Pairs the adapter and the station on it.

        Args:
            adapter: the lab adapter.
            station: the ground station on the adapter's pins.
        """
        self._adapter = adapter
        self._station = station
        self.period_s = adapter.period_s
        self.dictionary = station.dictionary
        self.build = adapter.build

    def boot(self) -> None:
        """Power-cycles the deployment, as the adapter does."""
        self._adapter.boot()

    def tick(self, t_ns: int, messages_by_role: Mapping[str, Any]) -> dict[str, Any]:
        """Steps the deployment, as the adapter does.

        Args:
            t_ns: ns, the tick's time.
            messages_by_role: each role's Basilisk message payload.

        Returns:
            The adapter's actuator commands, by role.
        """
        return self._adapter.tick(t_ns, messages_by_role)

    def uplink(self, name: str, args: Mapping[str, Any], context: int) -> None:
        """Queues a command, as the station does.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name.
            context: the ground's number for the command.
        """
        self._station.uplink(name, args, context)

    def responses(self) -> list[tuple[int, str, str | None]]:
        """The command responses since the last call, as the station gives them.

        Returns:
            The station's responses.
        """
        return self._station.responses()

    def telemetry(self) -> list[tuple[str, int, bytes]]:
        """Every telemetry write since the last call, as the station gives them.

        Returns:
            The station's writes.
        """
        return self._station.telemetry()

    def values(self, name: str, raws: Sequence[bytes]) -> np.ndarray:
        """One channel's writes as values, as the station decodes them.

        Args:
            name: `<instance>.<channel>`.
            raws: its writes' bytes.

        Returns:
            The station's values.
        """
        return self._station.values(name, raws)


@provides("SYS001")
def fprime_dead_reckoner(scenario: Scenario, prm_path: Path) -> FprimeBuild:
    """The F´ dead reckoner, booted idle on a scenario's vehicle.

    Args:
        scenario: the scenario whose vehicle the deployment flies on.
        prm_path: the case's parameter record.

    Returns:
        The F´ build of the dead reckoner's configuration.
    """
    adapter = Adapter("ImuDeadReckoning", prm_path)
    return FprimeBuild(adapter, FprimeStation(adapter, adapter.dictionary))


# %%
PYTHON = Mission(
    vehicle="imu_spacecraft",
    fsw=dead_reckoner,
    parameters=parameters,
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
#     python = load_runs(f"Test_imu_spacecraft::test_dead_reckoner_{scenario}")
#     fprime = load_runs(f"Test_imu_spacecraft::test_fprime_dead_reckoner_{scenario}")
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
