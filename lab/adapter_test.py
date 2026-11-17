"""The lab adapter: each configuration's F´ build as a WiseDynamics FSW build, on its sensor bytes.

Skipped without every deployment `just fsw` builds.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from fsw.codegen.deployment import configurations, tick_period
from ground.fprime_station import FprimeStation
from lab import Adapter, built

if not all(built(c) for c in configurations()):
    pytest.skip("an F´ build is absent; run `just fsw`", allow_module_level=True)

REPOSITORY = Path(__file__).parents[1]

NS = 1_000_000_000
"""ns per s."""


def test_the_adapter_ticks_at_its_configuration_s_base_tick_and_commands_nothing(
    configuration: str, messages_by_role: dict[str, Any], prm_record: Path
):
    """Booted, each tick on every role's message returns no command.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each role the CDH converts.
        prm_record: the case's parameter record.
    """
    adapter = Adapter(configuration, prm_record)

    adapter.boot()

    assert adapter.period_s == tick_period(configuration)
    assert adapter.tick(NS, messages_by_role) == {}
    assert adapter.tick(2 * NS, messages_by_role) == {}


def test_the_adapter_makes_the_case_s_dat_beside_its_record(configuration: str, prm_record: Path):
    """The `.dat` PrmDb boots on is made beside the record when the adapter is built.

    Args:
        configuration: the configuration.
        prm_record: the case's parameter record.
    """
    Adapter(configuration, prm_record)

    assert prm_record.with_suffix("").with_suffix(".prm.dat").is_file()


def test_each_boot_power_cycles_a_fresh_copy(
    configuration: str, messages_by_role: dict[str, Any], prm_record: Path
):
    """A second boot powers on another copy, where one copy refuses a second boot.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each role the CDH converts.
        prm_record: the case's parameter record.
    """
    adapter = Adapter(configuration, prm_record)
    adapter.boot()
    adapter.tick(NS, messages_by_role)

    adapter.boot()

    assert adapter.tick(NS, messages_by_role) == {}


def test_a_tick_missing_a_role_the_cdh_converts_is_refused_naming_it(
    configuration: str, messages_by_role: dict[str, Any], prm_record: Path
):
    """A tick without a converted role's message names the role and the messages it was given.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each role the CDH converts.
        prm_record: the case's parameter record.
    """
    adapter = Adapter(configuration, prm_record)
    adapter.boot()
    role = sorted(messages_by_role)[0]
    messages = {other: m for other, m in messages_by_role.items() if other != role}

    given = sorted(messages)
    lacking = re.escape(f"takes the role {role}, which the vehicle's messages {given} lack")
    with pytest.raises(KeyError, match=lacking):
        adapter.tick(NS, messages)


@pytest.mark.parametrize("excess_ns", [1, 500, 999])
def test_a_tick_that_is_not_a_whole_microsecond_is_refused_naming_its_time(
    configuration: str, messages_by_role: dict[str, Any], prm_record: Path, excess_ns: int
):
    """A tick at a whole microsecond steps; one nanoseconds past it raises, naming its time.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each role the CDH converts.
        prm_record: the case's parameter record.
        excess_ns: ns past a whole microsecond.
    """
    adapter = Adapter(configuration, prm_record)
    adapter.boot()
    whole = NS + 1_000
    adapter.tick(whole, messages_by_role)

    with pytest.raises(RuntimeError, match=f"tick at {whole + excess_ns} ns "):
        adapter.tick(whole + excess_ns, messages_by_role)


def test_an_adapter_checks_its_f_prime_build_before_it_makes_the_case_s_dat(
    configuration: str, monkeypatch: pytest.MonkeyPatch, prm_record: Path
):
    """With no extension to import, building an adapter raises as `source` does, before any `.dat`.

    Args:
        configuration: the configuration.
        monkeypatch: hides the extension from the import system.
        prm_record: the case's parameter record.
    """
    monkeypatch.setitem(sys.modules, f"lab._wise_fsw_{configuration}", None)

    with pytest.raises(ModuleNotFoundError, match="not built; run `just fsw`"):
        Adapter(configuration, prm_record)
    assert not prm_record.with_suffix("").with_suffix(".prm.dat").exists()


def test_the_build_names_the_pinned_framework_tag_and_the_project_version(
    configuration: str, prm_record: Path
):
    """`build` is the adapter, the F´ tag the justfile pins and the dictionary's project version.

    Args:
        configuration: the configuration.
        prm_record: the case's parameter record.
    """
    build = Adapter(configuration, prm_record).build

    tag = subprocess.run(
        ["just", "--evaluate", "fprime_tag"], cwd=REPOSITORY, capture_output=True, text=True
    ).stdout.strip()
    assert set(build) == {"host", "frameworkVersion", "projectVersion"}
    assert build["host"] == "lab.Adapter"
    assert build["frameworkVersion"] == tag
    assert tag
    assert isinstance(build["projectVersion"], str)
    assert build["projectVersion"]


def test_a_command_goes_up_to_the_current_copy_and_its_response_comes_back(
    configuration: str, messages_by_role: dict[str, Any], prm_record: Path
):
    """Through the station on the adapter, a command runs at the next tick, answered by context.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each role the CDH converts.
        prm_record: the case's parameter record.
    """
    adapter = Adapter(configuration, prm_record)
    station = FprimeStation(adapter, adapter.dictionary)
    adapter.boot()

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 4)
    assert station.responses() == []
    adapter.tick(NS, messages_by_role)

    assert station.responses() == [(4, "OK", None)]
    assert station.period_s == adapter.period_s


def test_the_telemetry_is_every_write_the_ticks_drained_since_the_last_call(
    configuration: str, messages_by_role: dict[str, Any], prm_record: Path
):
    """Two ticks' writes come down together, each tagged with its tick, then none until the next.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each role the CDH converts.
        prm_record: the case's parameter record.
    """
    adapter = Adapter(configuration, prm_record)
    adapter.boot()

    adapter.tick(NS, messages_by_role)
    adapter.tick(2 * NS, messages_by_role)
    writes = adapter.telemetry()

    assert [t_ns for _, t_ns, _ in writes] == sorted(t_ns for _, t_ns, _ in writes)
    assert {t_ns for _, t_ns, _ in writes} == {NS, 2 * NS}
    assert all(isinstance(raw, bytes) for _, _, raw in writes)
    assert adapter.telemetry() == []


def test_a_boot_drops_the_writes_an_earlier_copy_left_undrained(
    configuration: str, messages_by_role: dict[str, Any], prm_record: Path
):
    """A power cycle keeps no write of the copy before it.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each role the CDH converts.
        prm_record: the case's parameter record.
    """
    adapter = Adapter(configuration, prm_record)
    adapter.boot()
    adapter.tick(NS, messages_by_role)
    assert adapter._writes

    adapter.boot()

    assert adapter.telemetry() == []
