"""The lab adapter: each configuration's F´ build as a WiseDynamics FSW build, on its bus bytes.

Each configuration's sensor bytes go in; the test mock `MockActuation`'s actuator bytes come back
as commands. Skipped without every deployment `just fsw` builds.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from fsw.codegen import fpp_types
from fsw.codegen.deployment import (
    REPOSITORY,
    configuration_model,
    fprime_configurations,
    tick_period,
)
from fsw.codegen.roles import taken
from fsw.mock import MOCK
from fsw.mock.actuator.actuator import Actuator
from fsw.payloads import payload_type
from fsw.python.cdh import outputs
from fsw.python.rio.messages import commands
from ground.fprime_station import FprimeStation
from lab import Adapter, built

if not all(built(c) for c in fprime_configurations()):
    pytest.skip("an F´ build is absent; run `just fsw`", allow_module_level=True)


NS = 1_000_000_000
"""ns per s."""


@pytest.fixture
def adapter(fprime_configuration: str, prm_record: Path) -> Adapter:
    """The configuration's adapter on the case's record, booted.

    Args:
        fprime_configuration: the configuration.
        prm_record: the case's parameter record.

    Returns:
        The adapter.
    """
    adapter = Adapter(fprime_configuration, prm_record)
    adapter.boot()
    return adapter


def _assert_commands_of_its_actuators(configuration: str, commands: dict[str, Any]) -> None:
    """A tick's commands are of the configuration's actuator roles, each its payload class.

    Args:
        configuration: the configuration.
        commands: what a tick returned, by role.
    """
    actuators = {
        role.role: role
        for role in taken(configuration_model(configuration), configuration)
        if not role.sensor
    }
    assert set(commands) <= set(actuators), sorted(commands)
    for role, payload in commands.items():
        assert type(payload) is payload_type(actuators[role].bus), role


def test_the_adapter_ticks_at_its_configuration_s_base_tick_and_commands_only_its_actuators(
    configuration: str, messages_by_role: dict[str, Any], adapter: Adapter
):
    """Booted, each tick returns commands of the configuration's actuator roles alone, if any.

    A configuration taking no actuator role commands nothing.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    assert adapter.period_s == tick_period(configuration)
    for k in (1, 2):
        _assert_commands_of_its_actuators(configuration, adapter.tick(k * NS, messages_by_role))


def test_the_adapter_delivers_each_role_s_message_on_its_lab_bus_driver_port(
    adapter: Adapter,
    messages_by_role: dict[str, Any],
    bus: list[tuple[int, bytes]],
    monkeypatch: pytest.MonkeyPatch,
):
    """A tick steps the copy with each role's message, as the bus emulator writes it, on its port.

    Args:
        adapter: the configuration's adapter, booted.
        messages_by_role: a message for each sensor role the configuration takes.
        bus: every sensor role's bus message on its LabBusDriver port.
        monkeypatch: records the bus each step of the copy takes.
    """
    stepped = []
    step = adapter._fsw.step

    def recorded(t_ns: int, bus: list[tuple[int, bytes]]) -> list[tuple[int, bytes]]:
        """Records the step's bus, then steps the copy.

        Args:
            t_ns: ns, the step's time.
            bus: the step's `(port, bytes)` pairs.

        Returns:
            What the step returns: the bytes its GNC sent each actuator port.
        """
        stepped.append(list(bus))
        return step(t_ns=t_ns, bus=bus)

    monkeypatch.setattr(adapter._fsw, "step", recorded)

    adapter.tick(NS, messages_by_role)

    assert len(stepped) == 1
    assert sorted(stepped[0]) == sorted(bus)


def test_the_adapter_makes_the_case_s_dat_beside_its_record(adapter: Adapter, prm_record: Path):
    """The `.dat` PrmDb boots on is made beside the record when the adapter is built.

    Args:
        adapter: the configuration's adapter, booted.
        prm_record: the case's parameter record.
    """
    assert prm_record.with_suffix("").with_suffix(".prm.dat").is_file()


def test_each_boot_power_cycles_a_fresh_copy(
    configuration: str, messages_by_role: dict[str, Any], adapter: Adapter
):
    """A second boot powers on another copy, where one copy refuses a second boot.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    adapter.tick(NS, messages_by_role)

    adapter.boot()

    _assert_commands_of_its_actuators(configuration, adapter.tick(NS, messages_by_role))


def test_a_tick_missing_a_role_the_cdh_converts_is_refused_naming_it(
    configuration: str, messages_by_role: dict[str, Any], adapter: Adapter
):
    """A tick without a converted role's message names the role and the messages it was given.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    if not messages_by_role:
        pytest.skip(f"{configuration} takes no sensor role")
    role = sorted(messages_by_role)[0]
    messages = {other: m for other, m in messages_by_role.items() if other != role}

    given = sorted(messages)
    lacking = re.escape(f"takes the role {role}, which the vehicle's messages {given} lack")
    with pytest.raises(KeyError, match=lacking):
        adapter.tick(NS, messages)


@pytest.mark.parametrize("excess_ns", [1, 500, 999])
def test_a_tick_that_is_not_a_whole_microsecond_is_refused_naming_its_time(
    messages_by_role: dict[str, Any], adapter: Adapter, excess_ns: int
):
    """A tick at a whole microsecond steps; one nanoseconds past it raises, naming its time.

    Args:
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
        excess_ns: ns past a whole microsecond.
    """
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


def test_the_build_names_the_pinned_framework_tag_and_the_project_version(adapter: Adapter):
    """`build` is the adapter, the F´ tag the justfile pins and the dictionary's project version.

    Args:
        adapter: the configuration's adapter, booted.
    """
    build = adapter.build

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
    messages_by_role: dict[str, Any], adapter: Adapter
):
    """Through the station on the adapter, a command runs at the next tick, answered by context.

    Args:
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    station = FprimeStation(adapter, adapter.dictionary)

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 4)
    assert station.responses() == []
    adapter.tick(NS, messages_by_role)

    assert station.responses() == [(4, "OK", None)]
    assert station.period_s == adapter.period_s


def test_the_telemetry_is_every_write_the_ticks_drained_since_the_last_call(
    messages_by_role: dict[str, Any], adapter: Adapter
):
    """Two ticks' writes come down together, each tagged with its tick, then none until the next.

    Args:
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    adapter.tick(NS, messages_by_role)
    adapter.tick(2 * NS, messages_by_role)
    writes = adapter.telemetry()

    assert [t_ns for _, t_ns, _ in writes] == sorted(t_ns for _, t_ns, _ in writes)
    assert {t_ns for _, t_ns, _ in writes} == {NS, 2 * NS}
    assert all(isinstance(raw, bytes) for _, _, raw in writes)
    assert adapter.telemetry() == []


def test_a_boot_drops_the_writes_an_earlier_copy_left_undrained(
    messages_by_role: dict[str, Any], adapter: Adapter
):
    """A power cycle keeps no write of the copy before it.

    Args:
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    adapter.tick(NS, messages_by_role)
    assert adapter.telemetry()
    adapter.tick(2 * NS, messages_by_role)

    adapter.boot()

    assert adapter.telemetry() == []


def test_each_tick_returns_each_actuator_command_its_gnc_sent_as_its_message(tmp_path: Path):
    """MockActuation's adapter returns, each tick, the role's payload the Python build makes.

    The test mock sends its command each tick; the adapter reads the bytes back into a fresh
    `messaging.<Name>Payload` of the role's message, field for field the Python build's.

    Args:
        tmp_path: where the case's record is written.
    """
    configuration = "MockActuation"
    if not built(configuration):
        pytest.skip(f"the F´ build of {configuration} is absent; run `just fsw`")
    fpp_types.load(MOCK)
    [role] = taken(configuration_model(configuration, contract=MOCK), configuration)
    pairs = outputs.pairings([role])
    sent = Actuator(None).step(0.0)[0]
    python = commands(pairs, outputs.convert(pairs, {role.output: sent[0]}))[role.role]
    record = tmp_path / "run_0000.prm.json"
    record.write_text('{"MockActuation.actuator": {}}')
    adapter = Adapter(configuration, record, contract=MOCK)
    adapter.boot()

    for k in (1, 2):
        tick = adapter.tick(k * NS, {})
        assert list(tick) == [role.role]
        assert type(tick[role.role]) is type(python)
        for field in type(python).__dtype__.names:
            assert list(getattr(tick[role.role], field)) == list(getattr(python, field)), field
