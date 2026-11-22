"""Each case flies a fresh copy of the deployment: what one copy did never reaches the next.

That a whole flight carries nothing to the next case is a mission's, so it is tested in
`harness/mission_test.py`, `test_a_case_flown_after_another_writes_the_run_file_it_writes_alone`.
Skipped without the deployment `just fsw` builds.
"""

import os
import sys
from pathlib import Path

import pytest

from fsw.codegen.deployment import fprime_configurations
from fsw.codegen.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab.power_cycle import built, power_cycle, source

if not all(built(c) for c in fprime_configurations()):
    pytest.skip("an F´ build is absent; run `just fsw`", allow_module_level=True)

NS = 1_000_000_000
"""ns per s."""


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

    The later copy's rate groups count from 1 over its one tick and it answers nothing; the earlier
    one's count on from 1 over its own two ticks, and it answers both its commands.

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

    later_counts, earlier_counts = counts(later_station), counts(earlier_station)
    assert any(later_counts.values())
    for group in rate_groups:
        assert later_counts[group] in ([], [1]), group
        assert earlier_counts[group] == list(range(1, len(earlier_counts[group]) + 1)), group
        assert len(earlier_counts[group]) >= len(later_counts[group]), group
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Each configuration's extension is stamped apart: another's rebuild leaves it flying.

    The extensions are two stand-in modules in the test's directory, so no F´ build is touched.

    Args:
        tmp_path: where the stand-in extensions are written.
        monkeypatch: names the stand-ins as the extensions and empties the process's stamps.
    """
    for name in ("a", "b"):
        (tmp_path / f"fake_{name}.py").write_text("")
    monkeypatch.syspath_prepend(tmp_path)
    monkeypatch.setattr("lab.power_cycle._extension", lambda c: f"fake_{c}")
    monkeypatch.setattr("lab.power_cycle._loaded_stamps", {})
    source("a")
    source("b")

    status = (tmp_path / "fake_a.py").stat()
    os.utime(tmp_path / "fake_a.py", ns=(status.st_atime_ns, status.st_mtime_ns + NS))

    with pytest.raises(RuntimeError, match="rebuilt after this process loaded it.*restart"):
        source("a")
    assert source("b") == tmp_path / "fake_b.py"
