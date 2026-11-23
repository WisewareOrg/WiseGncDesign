"""The lab adapter: each configuration's F´ build as a WiseDynamics FSW build, on its bus bytes.

Each configuration's sensor bytes go in; the test mock `MockActuation`'s actuator bytes come back
as commands. Skipped without every deployment `just fsw` builds.
"""

import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from Basilisk.architecture.messaging.SCStatesMsgPayload import SCStatesMsgPayload

import lab.adapter as adapter_module
from fsw.codegen.deployment import (
    REPOSITORY,
    configuration_model,
    tick_period,
)
from fsw.codegen.roles import Role, taken
from fsw.mock import MOCK
from fsw.payloads import payload_type
from ground.fprime_station import FprimeStation
from lab import Adapter, built
from lab.bus_emulator import serialize

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
    if not built(fprime_configuration):
        pytest.skip(f"the F´ build of {fprime_configuration} is absent; run `just fsw`")
    adapter = Adapter(fprime_configuration, prm_record)
    adapter.boot()
    return adapter


def _clone(payload: Any) -> Any:
    """A fresh payload of the same class holding the same values.

    Args:
        payload: a Basilisk payload.

    Returns:
        The clone.
    """
    clone = type(payload)()
    for field in type(payload).__dtype__.names:
        setattr(clone, field, getattr(payload, field))
    return clone


def _assert_commands_of_its_actuators(configuration: str, commands: Mapping[str, Any]) -> None:
    """A tick's commands are of the configuration's actuator roles, each its payload class.

    Args:
        configuration: the configuration.
        commands: what a tick returned, by role.
    """
    actuators = {
        role.role: role for role in taken(configuration_model(configuration), configuration) if not role.sensor
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


def test_each_tick_writes_each_role_s_message_as_it_stands_into_its_receive_buffer(
    adapter: Adapter,
    configuration: str,
    messages_by_role: dict[str, Any],
    bus_by_role: dict[str, tuple[int, bytes]],
    monkeypatch: pytest.MonkeyPatch,
):
    """At each tick's step, the receive buffers hold that tick's messages, as the emulator writes them.

    The buffers are read when the copy steps, so a copy made after the step shows. The same
    mapping's payloads changed in place reach the next tick, as `FswHost`'s live views do, and a
    tick given another mapping writes that one's.

    Args:
        adapter: the configuration's adapter, booted.
        configuration: the configuration.
        messages_by_role: a message for each sensor role the configuration takes.
        bus_by_role: each sensor role's LabBusDriver port and message bytes.
        monkeypatch: records the next boot's copy's receive buffers as each step finds them.
    """
    if not bus_by_role:
        pytest.skip(f"{configuration} takes no sensor role")
    buffers: dict[int, memoryview] = {}
    stepped: list[dict[int, bytes]] = []
    cycle = adapter_module.power_cycle

    def recorded(configuration: str) -> Any:
        """A fresh copy whose receive buffers are recorded by port, and read at each step.

        Args:
            configuration: the configuration.

        Returns:
            The copy.
        """
        fsw = cycle(configuration)
        make = fsw.receive_buffer

        def receive_buffer(port: int, size: int) -> memoryview:
            """Makes the port's buffer and records it.

            Args:
                port: the port.
                size: its bytes.

            Returns:
                The buffer.
            """
            buffers[port] = make(port, size)
            return buffers[port]

        step = fsw.step

        def read_then_step(t_ns: int) -> int:
            """Records the receive buffers as the step finds them, then steps.

            Args:
                t_ns: ns, the step's time.

            Returns:
                What the step returns.
            """
            stepped.append({port: bytes(buffer) for port, buffer in buffers.items()})
            return step(t_ns)

        monkeypatch.setattr(fsw, "receive_buffer", receive_buffer)
        monkeypatch.setattr(fsw, "step", read_then_step)
        return fsw

    monkeypatch.setattr(adapter_module, "power_cycle", recorded)
    adapter.boot()
    first = dict(bus_by_role.values())
    others = {role: _clone(payload) for role, payload in messages_by_role.items()}

    adapter.tick(NS, messages_by_role)
    assert stepped[-1] == first

    for payload in messages_by_role.values():
        for field in type(payload).__dtype__.names:
            setattr(payload, field, [value + 1.0 for value in getattr(payload, field)])
    adapter.tick(2 * NS, messages_by_role)
    moved = {port: serialize(messages_by_role[role]) for role, (port, _) in bus_by_role.items()}
    assert moved != first
    assert stepped[-1] == moved

    adapter.tick(3 * NS, others)
    assert stepped[-1] == first


def test_a_role_s_message_of_another_class_is_refused_naming_both(
    configuration: str, messages_by_role: dict[str, Any], adapter: Adapter
):
    """A tick whose role's message is not the class its bus struct mirrors names both classes.

    Args:
        configuration: the configuration.
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    if not messages_by_role:
        pytest.skip(f"{configuration} takes no sensor role")
    role = sorted(messages_by_role)[0]
    wanted = type(messages_by_role[role]).__name__

    with pytest.raises(
        TypeError, match=f"role {role}'s message is a SCStatesMsgPayload, but its bus struct mirrors {wanted}"
    ):
        adapter.tick(NS, {**messages_by_role, role: SCStatesMsgPayload()})


def test_each_boot_power_cycles_a_fresh_copy(configuration: str, messages_by_role: dict[str, Any], adapter: Adapter):
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


def test_a_tick_that_is_not_a_whole_microsecond_is_refused_naming_its_time(
    messages_by_role: dict[str, Any], adapter: Adapter
):
    """A tick at a whole microsecond steps; one 500 ns past it raises, naming its time.

    Args:
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    whole = NS + 1_000
    adapter.tick(whole, messages_by_role)

    with pytest.raises(RuntimeError, match=f"tick at {whole + 500} ns "):
        adapter.tick(whole + 500, messages_by_role)


def test_the_build_names_the_pinned_framework_tag_and_the_project_version(adapter: Adapter):
    """`build` is the adapter, the F´ tag the justfile pins and the dictionary's project version.

    Args:
        adapter: the configuration's adapter, booted.
    """
    build = adapter.build

    tag = subprocess.run(
        ["just", "--evaluate", "fprime_tag"], cwd=REPOSITORY, capture_output=True, text=True
    ).stdout.strip()
    assert tag
    assert build["host"] == "lab.Adapter"
    assert build["frameworkVersion"] == tag
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


def test_a_boot_drops_the_writes_an_earlier_copy_left_undrained(messages_by_role: dict[str, Any], adapter: Adapter):
    """A power cycle keeps no write of the copy before it.

    The first tick's writes are drained, which shows a tick writes; the second tick's are left in
    the copy that the boot replaces.

    Args:
        messages_by_role: a message for each sensor role the configuration takes.
        adapter: the configuration's adapter, booted.
    """
    adapter.tick(NS, messages_by_role)
    assert adapter.telemetry()
    adapter.tick(2 * NS, messages_by_role)

    adapter.boot()

    assert adapter.telemetry() == []


def test_each_tick_returns_each_actuator_command_its_gnc_sent_as_its_message(
    mock_actuation: tuple[str, Role, Any, Path], holds: Callable[[Any, Mapping[str, Any]], None]
):
    """MockActuation's adapter returns, each tick, the role's payload the Python build makes.

    The test mock sends its command every other tick; the adapter reads the bytes back into the
    role's `messaging.<Name>Payload`, field for field the Python build's, returns the same commands
    each tick it sends, and none at a tick it does not.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
        holds: asserts a payload holds values.
    """
    configuration, role, python, record = mock_actuation
    adapter = Adapter(configuration, record, contract=MOCK)
    adapter.boot()

    ticks = []
    for k in (1, 3):
        tick = adapter.tick(k * NS, {})
        assert list(tick) == [role.role]
        assert type(tick[role.role]) is type(python)
        holds(tick[role.role], {f: getattr(python, f) for f in type(python).__dtype__.names})
        ticks.append(tick)
        assert adapter.tick((k + 1) * NS, {}) == {}
    assert ticks[1] is ticks[0]
