"""Each case flies a fresh copy of the deployment: what one case flew never reaches the next.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY as DICTIONARY_PATH
from lab.power_cycle import power_cycle

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

NS = 1_000_000_000
"""ns per s."""

DICTIONARY = Dictionary(DICTIONARY_PATH)
"""The deployment's dictionary, which the build generated."""

STATE = {
    "epoch": 0.0,
    "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
    "position": np.array([6871.0e3, 0.0, 0.0]),
    "velocity": np.array([0.0, 5.4e3, 5.4e3]),
}
"""`nav.initNavState`'s arguments: a state at t = 0."""

FLIGHT = """
from algorithms.imu_dead_reckoning import parameters
from harness.mission import Mission, mission_tests, provides
from lab import FprimeModule


@provides("SYS001")
def fprime(scenario, prm_path):
    return FprimeModule(scenario.vehicle.readers()["imu"], prm_path)


globals().update(
    mission_tests(
        Mission(vehicle="imu_spacecraft", fsw=fprime, scenarios=("TST001",), parameters=parameters)
    )
)
"""
"""The F´ build flown through the repository's leo500 scenario, TST001."""


def _contents(path: Path) -> dict[str, object]:
    """Every dataset of a run file, and every root attribute but its creation time.

    Args:
        path: the run file.

    Returns:
        Each dataset's values and attributes by its path, and each root attribute by `@<name>`.
    """
    contents: dict[str, object] = {}

    def visit(name: str, node: object) -> None:
        """Keep a dataset's values and attributes.

        Args:
            name: the node's path in the file.
            node: the group or dataset.
        """
        if isinstance(node, h5py.Dataset):
            contents[name] = (node[()], dict(node.attrs))

    with h5py.File(path, "r") as f:
        f.visititems(visit)
        contents |= {f"@{k}": v for k, v in f.attrs.items() if k != "created_utc"}
    return contents


def test_a_case_flown_after_another_writes_the_run_file_it_writes_alone(
    pytester: pytest.Pytester,
):
    """Case 1 flown alone and after case 0 in one process gives the same run file, every row.

    The rate group's health datasets are compared with nav's: its `CycleCount` and the channels it
    writes only on change are what a deployment kept across cases would carry over. Case 0's run
    file differs from case 1's, so a comparison that cannot tell cases apart would show.

    Args:
        pytester: the project the flights run in, each run in one process of its own, xdist off.
    """
    pytester.makepyfile(test_flights=FLIGHT)
    test = "test_flights.py::Test_imu_spacecraft::test_fprime_leo500"

    options = ("-p", "no:cacheprovider", "-p", "no:xdist")

    pytester.runpytest_subprocess(*options, f"{test}[1]").assert_outcomes(passed=1)
    [alone] = pytester.path.rglob("run_0001.h5")
    alone = shutil.move(alone, pytester.path / "alone.h5")
    pytester.runpytest_subprocess(*options, f"{test}[0]", f"{test}[1]").assert_outcomes(passed=2)
    [first] = pytester.path.rglob("run_0000.h5")
    [after] = pytester.path.rglob("run_0001.h5")

    alone, after, first = _contents(alone), _contents(after), _contents(first)
    assert any(name.startswith("tlm/nav.") for name in alone)
    assert any(name.startswith("tlm/navRateGroup.") for name in alone)
    assert sorted(alone) == sorted(after)
    for name, value in alone.items():
        np.testing.assert_equal(after[name], value, err_msg=name)
    with pytest.raises(AssertionError):
        np.testing.assert_equal(first, alone)


def test_an_f_prime_assert_raises_and_the_next_power_cycle_flies_a_fresh_copy(
    prm: str, parameter_ids: list[int]
):
    """A pin called before boot trips an F´ assert, raised in Python with F´'s own text.

    The copy that raised is never handed out again: the next power cycle is another module, which
    boots and steps. Neither copy is in `sys.modules`.

    Args:
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    raised = power_cycle()

    with pytest.raises(RuntimeError, match=r'^Assert: ".*:\d+"'):
        raised.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    fresh = power_cycle()
    assert fresh is not raised
    fresh.boot(prm, parameter_ids)
    fresh.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
    assert fresh.telemetry()
    assert raised not in sys.modules.values()
    assert fresh not in sys.modules.values()


def test_two_copies_in_one_process_share_no_state(prm: str, parameter_ids: list[int]):
    """A copy left mid-flight, a command queued and its link undrained, reaches no later copy.

    The later copy boots idle and answers nothing; the earlier one flies on from its own state.

    Args:
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    zero = {"angVelPlatform": np.zeros(3), "accelPlatform": np.zeros(3)}
    earlier, later = power_cycle(), power_cycle()
    earlier_station = FprimeStation(earlier, DICTIONARY)
    later_station = FprimeStation(later, DICTIONARY)
    earlier.boot(prm, parameter_ids)
    earlier_station.uplink("nav.initNavState", STATE, 1)
    earlier.step(t_ns=NS, **zero)
    earlier_station.uplink("nav.initNavState", STATE, 2)

    later.boot(prm, parameter_ids)
    later.step(t_ns=NS, **zero)
    earlier.step(t_ns=2 * NS, **zero)

    def nav_states(station: FprimeStation) -> list[tuple[int, str]]:
        """Drains a station's telemetry and keeps nav's state writes.

        Args:
            station: the station on one copy.

        Returns:
            Each `nav.navState` write's F´ time tag and value, oldest first.
        """
        writes = [(t, raw) for name, t, raw in station.telemetry() if name == "nav.navState"]
        values = station.values("nav.navState", [raw for _, raw in writes])
        return [(t, value) for (t, _), value in zip(writes, values.tolist(), strict=True)]

    assert nav_states(later_station) == [(NS, "idle")]
    assert later_station.responses() == []
    assert nav_states(earlier_station)[-1] == (2 * NS, "propagated")
    assert [context for context, _, _ in earlier_station.responses()] == [1, 2]


def test_a_copy_boots_once(prm: str, parameter_ids: list[int]):
    """A second boot of one copy is refused: a copy is powered on once.

    Args:
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    copy = power_cycle()
    copy.boot(prm, parameter_ids)

    with pytest.raises(RuntimeError, match="already booted"):
        copy.boot(prm, parameter_ids)
