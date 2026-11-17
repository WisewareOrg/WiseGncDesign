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

from fsw.codegen.deployment import configurations
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab.power_cycle import _loaded_stamps, dictionary_path, power_cycle, source

if not all(importlib.util.find_spec(f"lab._wise_fsw_{c}") for c in configurations()):
    pytest.skip("an F´ build is absent; run `just fsw`", allow_module_level=True)

NS = 1_000_000_000
"""ns per s."""

STATE = {
    "epoch": 0.0,
    "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
    "position": np.array([6871.0e3, 0.0, 0.0]),
    "velocity": np.array([0.0, 5.4e3, 5.4e3]),
}
"""`nav.initNavState`'s arguments: a state at t = 0."""

FLIGHT = """
from algorithms.imu_dead_reckoning import parameters
from algorithms.imu_dead_reckoning.parity import fprime_dead_reckoner as fprime
from harness.mission import Mission, mission_tests


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
    test = "test_flights.py::Test_imu_spacecraft::test_fprime_dead_reckoner_leo500"

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
    configuration: str, prm: str, parameter_ids: list[int], bus: list[tuple[int, bytes]]
):
    """A pin called before boot trips an F´ assert, raised in Python with F´'s own text.

    The copy that raised is never handed out again: the next power cycle is another module, which
    boots and steps. Neither copy is in `sys.modules`.

    Args:
        configuration: the configuration power-cycled.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    raised = power_cycle(configuration)

    with pytest.raises(RuntimeError, match=r'^Assert: ".*:\d+"'):
        raised.step(t_ns=NS, bus=bus)

    fresh = power_cycle(configuration)
    assert fresh is not raised
    fresh.boot(prm, parameter_ids)
    fresh.step(t_ns=NS, bus=bus)
    assert fresh.telemetry()
    assert raised not in sys.modules.values()
    assert fresh not in sys.modules.values()


def test_two_copies_in_one_process_share_no_state(
    configuration: str,
    dictionary: Dictionary,
    rate_groups: list[str],
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """A copy left mid-flight, a command queued and its link undrained, reaches no later copy.

    The later copy's rate groups count its one tick and it answers nothing; the earlier one's count
    its own two ticks, and it answers both its commands.

    Args:
        configuration: the configuration power-cycled.
        dictionary: its dictionary.
        rate_groups: its rate groups.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    assert rate_groups
    earlier, later = power_cycle(configuration), power_cycle(configuration)
    earlier_station = FprimeStation(earlier, dictionary)
    later_station = FprimeStation(later, dictionary)
    earlier.boot(prm, parameter_ids)
    earlier_station.uplink("cmdDisp.CMD_NO_OP", {}, 1)
    earlier.step(t_ns=NS, bus=bus)
    earlier_station.uplink("cmdDisp.CMD_NO_OP", {}, 2)

    later.boot(prm, parameter_ids)
    later.step(t_ns=NS, bus=bus)
    earlier.step(t_ns=2 * NS, bus=bus)

    def counts(station: FprimeStation) -> dict[str, list[int]]:
        """Drains a station's telemetry and keeps each rate group's `CycleCount` writes.

        Args:
            station: the station on one copy.

        Returns:
            Each rate group's counts, oldest first.
        """
        writes = station.telemetry()
        names = {group: f"{group}.CycleCount" for group in rate_groups}
        return {
            group: station.values(name, [raw for n, _, raw in writes if n == name]).tolist()
            for group, name in names.items()
        }

    assert counts(later_station) == {group: [1] for group in rate_groups}
    assert counts(earlier_station) == {group: [1, 2] for group in rate_groups}
    assert later_station.responses() == []
    assert [context for context, _, _ in earlier_station.responses()] == [1, 2]


def test_a_copy_boots_once(configuration: str, prm: str, parameter_ids: list[int]):
    """A second boot of one copy is refused: a copy is powered on once.

    Args:
        configuration: the configuration power-cycled.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    copy = power_cycle(configuration)
    copy.boot(prm, parameter_ids)

    with pytest.raises(RuntimeError, match="already booted"):
        copy.boot(prm, parameter_ids)


def test_a_configuration_not_built_is_refused_naming_it():
    """A configuration with no extension names itself and the recipe that builds it."""
    with pytest.raises(
        ModuleNotFoundError, match=r"of NoSuchConfiguration is not built; run `just fsw`"
    ):
        source("NoSuchConfiguration")


def test_a_rebuilt_extension_is_refused_by_its_own_configuration_alone(
    configuration: str, monkeypatch: pytest.MonkeyPatch
):
    """Each configuration's extension is stamped apart: another's rebuild leaves it flying.

    Args:
        configuration: the configuration checked.
        monkeypatch: records a different file as the one this process loaded.
    """
    monkeypatch.setitem(_loaded_stamps, f"Other{configuration}", (-1, -1))
    assert power_cycle(configuration)

    monkeypatch.setitem(_loaded_stamps, configuration, (-1, -1))
    with pytest.raises(RuntimeError, match="rebuilt after this process loaded it.*restart"):
        power_cycle(configuration)


def test_a_configuration_s_dictionary_is_the_one_its_deployment_generated(
    configuration: str, dictionary: Dictionary
):
    """`dictionary_path` names the dictionary of the configuration's own deployment.

    Args:
        configuration: the configuration.
        dictionary: the dictionary at its path.
    """
    assert dictionary_path(configuration).name == f"{configuration}FswTopologyDictionary.json"
    assert dictionary.metadata["deploymentName"] == f"WiseFsw.{configuration}Fsw"
