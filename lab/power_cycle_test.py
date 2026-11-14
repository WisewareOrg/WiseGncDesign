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

from lab.power_cycle import power_cycle

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

MU = 3.986004360e14
"""m^3/s^2, Earth's gravitational parameter, as the scenarios set it."""

NS = 1_000_000_000
"""ns per s."""

FLIGHT = """
import numpy as np

from harness.mission import Mission, mission_tests, provides
from lab import FprimeModule


@provides("SYS001")
def fprime(scenario):
    return FprimeModule(
        scenario.vehicle.readers()["imu"],
        mu=scenario.mu_m3_s2["earth"],
        dcm_PB=np.asarray(scenario.vehicle.imu.dcm_PB),
    )


globals().update(
    mission_tests(Mission(vehicle="imu_spacecraft", fsw=fprime, scenarios=("TST001",)))
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
        pytester: the project the flights run in, each in a process of its own.
    """
    pytester.makepyfile(test_flights=FLIGHT)
    test = "test_flights.py::Test_imu_spacecraft::test_fprime_leo500"

    pytester.runpytest_subprocess("-p", "no:cacheprovider", f"{test}[1]").assert_outcomes(passed=1)
    [alone] = pytester.path.rglob("run_0001.h5")
    alone = shutil.move(alone, pytester.path / "alone.h5")
    pytester.runpytest_subprocess(
        "-p", "no:cacheprovider", f"{test}[0]", f"{test}[1]"
    ).assert_outcomes(passed=2)
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


def test_an_f_prime_assert_raises_and_the_next_power_cycle_flies_a_fresh_copy():
    """A pin called before boot trips an F´ assert, raised in Python with F´'s own text.

    The copy that raised is never handed out again: the next power cycle is another module, which
    boots and steps. Neither copy is in `sys.modules`.
    """
    raised = power_cycle()

    with pytest.raises(RuntimeError, match=r'^Assert: ".*:\d+"'):
        raised.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    fresh = power_cycle()
    assert fresh is not raised
    fresh.boot(mu=MU, dcm_PB=np.eye(3))
    fresh.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
    assert fresh.telemetry()
    assert raised not in sys.modules.values()
    assert fresh not in sys.modules.values()


def test_a_copy_boots_once():
    """A second boot of one copy is refused: a copy is powered on once."""
    copy = power_cycle()
    copy.boot(mu=MU, dcm_PB=np.eye(3))

    with pytest.raises(RuntimeError, match="already booted"):
        copy.boot(mu=MU, dcm_PB=np.eye(3))
