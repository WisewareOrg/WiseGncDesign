"""The Python build's frame runner, on mock GNC sub-topologies of mock algorithms.

The mock, `MockFrame` of `fsw.mock.MOCK`, flies two mock algorithms: a source, run every tick,
whose sample feeds a sink, run every second tick, and a command on the source; it takes no role. A
second mock, rendered from the contract into a temporary directory, takes every role the contract
declares at one device, so a tick's sensor messages are read and converted, and its actuator
commands converted and written, on the runner's own path. The mock algorithms,
`fsw.mock.mock_gnc`, are named as their FPP components; they log what they are given and write what
each test needs.
"""

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.codegen.deployment import Contract, configuration_model
from fsw.codegen.dictionary import Dictionary
from fsw.codegen.fpp_types import named
from fsw.codegen.roles import Role, roles
from fsw.mock import MOCK, device_contract, exposure
from fsw.mock.mock_gnc import LOG, Sink, Source
from fsw.payloads import payload_type
from fsw.python import FrameRunner

CONFIGURATION = "MockFrame"
"""The mock's configuration."""

NS = 1_000_000_000
"""ns per s."""

RECORD = {f"{CONFIGURATION}.source": {"gain": 2.5}, f"{CONFIGURATION}.sink": {"offset": 0.25}}
"""The case's record, as the ground writes one, keyed by each instance's qualified name."""


@pytest.fixture
def runner(tmp_path: Path) -> FrameRunner:
    """The mock configuration, flown with the mock algorithms, booted, the log cleared.

    Args:
        tmp_path: where the case's record is written.

    Returns:
        The frame runner.
    """
    record = tmp_path / "run_0000.prm.json"
    record.write_text(json.dumps(RECORD))
    runner = FrameRunner(CONFIGURATION, record, (Source, Sink), contract=MOCK)
    runner.boot()
    LOG.clear()
    return runner


def test_the_frame_runner_is_the_mock_configuration_s_build(runner: FrameRunner):
    """Its period is the mock's base tick, and its dictionary the mock sub-topology's.

    Args:
        runner: the frame runner.
    """
    assert runner.period_s == 0.5
    assert runner.build == {"host": "fsw.python.FrameRunner"}
    generated = Dictionary.from_sub_topology(CONFIGURATION, contract=MOCK)
    assert generated.metadata["deploymentName"] == f"Py{CONFIGURATION}.Py{CONFIGURATION}"
    assert runner.dictionary.entries("source") == {
        "commands": {
            "GAIN_PRM_SET": [["val", "F64"]],
            "GAIN_PRM_SAVE": [],
            "setLevel": [["level", "F64"]],
            "reset": [],
        },
        "channels": {"level": ["F64", None]},
    }


def test_boot_builds_each_algorithm_on_its_record_parameters(runner: FrameRunner):
    """Each boot is a power cycle: a new algorithm on the parameters the case's record holds.

    Args:
        runner: the frame runner.
    """
    runner.boot()

    boots = {instance: parameters for instance, kind, parameters in LOG if kind == "boot"}
    assert boots == {
        "source": named("MockGnc.SourceParameters")(gain=2.5),
        "sink": named("MockGnc.SinkParameters")(offset=0.25),
    }


def test_the_data_connection_delivers_within_the_frame_in_rate_group_order(runner: FrameRunner):
    """The sink, run after the source on its divider's ticks, holds that frame's sample.

    The source runs every tick, the sink every second from the first, as F´'s rate-group driver
    counts: over two ticks the source steps twice, and the sink once, on the first tick, after the
    source in its frame, with the sample the source just sent.

    Args:
        runner: the frame runner.
    """
    runner.uplink("source.setLevel", {"level": 4.0}, 1)

    runner.tick(1 * NS // 2, {})
    runner.tick(2 * NS // 2, {})

    steps = [entry for entry in LOG if entry[1] == "step"]
    assert [(instance, t) for instance, _, t, *_ in steps] == [
        ("source", 0.5),
        ("sink", 0.5),
        ("source", 1.0),
    ]
    [(_, _, t, sample)] = [entry for entry in steps if entry[0] == "sink"]
    assert sample.value == 2.5 * 4.0 + t


def test_commands_run_by_name_before_the_step_and_answer_with_f_prime_s_responses(
    runner: FrameRunner,
):
    """Each command uplinked runs at the next tick, before the step, its telemetry tagged then.

    Taken and refused with its reason, each is answered as F´ answers it.

    Args:
        runner: the frame runner.
    """
    runner.uplink("source.setLevel", {"level": 1.5}, 7)
    runner.uplink("source.setLevel", {"level": -1.0}, 8)
    assert runner.responses() == []

    runner.tick(NS // 2, {})

    assert [(instance, kind) for instance, kind, *_ in LOG][:2] == [
        ("source", "setLevel"),
        ("source", "step"),
    ]
    assert runner.responses() == [
        (7, "OK", None),
        (8, "VALIDATION_ERROR", "level -1.0 is negative"),
    ]
    assert runner.responses() == []
    assert [(name, t_ns) for name, t_ns, _ in runner.telemetry()][:2] == [
        ("source.level", NS // 2),
        ("source.level", NS // 2),
    ]


def test_the_telemetry_is_each_write_of_the_frame_tagged_with_its_time(runner: FrameRunner):
    """Each tick's writes come down tagged with its time, valued as written, once.

    Args:
        runner: the frame runner.
    """
    runner.uplink("source.setLevel", {"level": 2.0}, 1)
    runner.tick(NS // 2, {})
    runner.tick(NS, {})

    writes = runner.telemetry()

    assert [t_ns for _, t_ns, _ in writes] == sorted(t_ns for _, t_ns, _ in writes)
    assert {t_ns for _, t_ns, _ in writes} == {NS // 2, NS}
    received = [(t_ns, raw) for name, t_ns, raw in writes if name == "sink.received"]
    [(t_ns, raw)] = received
    np.testing.assert_array_equal(runner.values("sink.received", [raw]), [2.5 * 2.0 + t_ns / NS + 0.25])
    assert runner.telemetry() == []


def test_boot_drops_every_command_response_and_write_not_yet_drained(runner: FrameRunner):
    """A power cycle keeps nothing of the last flight: no queued command, response or write.

    Args:
        runner: the frame runner.
    """
    runner.uplink("source.setLevel", {"level": 1.0}, 7)
    runner.tick(NS // 2, {})
    runner.uplink("source.setLevel", {"level": 2.0}, 8)

    runner.boot()
    runner.tick(NS // 2, {})

    assert runner.responses() == []
    writes = runner.telemetry()
    assert {t_ns for _, t_ns, _ in writes} == {NS // 2}
    assert [name for name, _, _ in writes].count("source.level") == 1
    [raw] = [raw for name, _, raw in writes if name == "source.level"]
    assert runner.values("source.level", [raw]).tolist() == [0.0]


class MockDevice:
    """The mock that takes every role: it logs each step's inputs, and writes its commands.

    It writes each actuator role's command, `commands`, on its odd-numbered steps, counted by its
    own step count from 1, and nothing on the others.

    Attributes:
        commands: each actuator role's command, an ICD struct's tuple, by its output port.
    """

    commands: dict[str, Any] = {}

    def __init__(self, parameters: Any) -> None:
        """Logs its parameters, which are none, and starts counting its steps.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        LOG.append(("device", "boot", parameters))
        self._steps = 0

    def step(self, t: float, **inputs: Any) -> tuple[Any, Any]:
        """Logs the step and its inputs, and writes the commands on an odd-numbered step.

        Args:
            t: s, the time.
            **inputs: each sensor role's input, by the role.

        Returns:
            Each actuator role's command on an odd-numbered step, else nothing, and no telemetry.
        """
        self._steps += 1
        LOG.append(("device", "step", t, inputs))
        written = self.commands if self._steps % 2 else dict.fromkeys(self.commands)
        return named("MockGnc.MockDeviceOutputs")(**written), named("MockGnc.MockDeviceTelemetry")()


@pytest.fixture(scope="session")
def roles_contract(tmp_path_factory: pytest.TempPathFactory) -> tuple[Contract, list[Role]]:
    """A mock contract whose one device takes every role the repository's contract declares.

    Rendered once per session: `fpp_types.load` holds the device as defined at one path, so a
    render at another path would define it again.

    Args:
        tmp_path_factory: where the mock is rendered.

    Returns:
        The contract, whose one configuration is `MockRoles`, and the roles.
    """
    declared = roles(configuration_model(CONFIGURATION, contract=MOCK))
    directory = tmp_path_factory.mktemp("roles")
    ports = [exposure(role) for role in declared]
    contract = device_contract(directory, "MockRoles", declared, ports, component="MockDevice")
    return contract, declared


@pytest.fixture
def roles_runner(
    roles_contract: tuple[Contract, list[Role]],
    icd_messages: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FrameRunner:
    """The rendered mock configuration, flown with `MockDevice`, booted, the log cleared.

    The device's commands are `icd_messages`' values of each actuator role's ICD struct.

    Args:
        roles_contract: the rendered contract and the roles.
        icd_messages: a value of each ICD struct, its members' values distinct.
        tmp_path: where the case's record is written.
        monkeypatch: sets the device's commands for the test.

    Returns:
        The frame runner.
    """
    commands = {r.output: icd_messages[r.icd].value for r in roles_contract[1] if not r.sensor}
    monkeypatch.setattr(MockDevice, "commands", commands)
    record = tmp_path / "run_0000.prm.json"
    record.write_text(json.dumps({"MockRoles.device": {}}))
    runner = FrameRunner("MockRoles", record, (MockDevice,), contract=roles_contract[0])
    runner.boot()
    LOG.clear()
    return runner


def _sensor_messages(declared: list[Role], bus_messages: dict[str, Any]) -> dict[str, Any]:
    """Each sensor role's message, as the host gives a build them.

    Args:
        declared: the roles.
        bus_messages: a message of each bus struct.

    Returns:
        Each sensor role's payload, by the role.
    """
    return {role.role: bus_messages[role.bus].payload for role in declared if role.sensor}


def test_each_role_s_message_reaches_the_step_as_its_icd_struct(
    roles_runner: FrameRunner,
    roles_contract: tuple[Contract, list[Role]],
    bus_messages: dict[str, Any],
    holds: Callable[[Any, Mapping[str, Any]], None],
):
    """A tick reads each sensor role's message and converts it, so the step gets its ICD struct.

    Each ICD field is its bus namesake's, ignoring case, by `fsw.codegen.fields`' rule.

    Args:
        roles_runner: the frame runner on the rendered mock.
        roles_contract: the rendered contract and the roles.
        bus_messages: a message of each bus struct, its members' values distinct.
        holds: asserts a tuple holds values.
    """
    sensors = [role for role in roles_contract[1] if role.sensor]
    assert sensors

    roles_runner.tick(NS, _sensor_messages(roles_contract[1], bus_messages))

    [(_, _, t, inputs)] = [entry for entry in LOG if entry[1] == "step"]
    assert t == 1.0
    assert set(inputs) == {role.role for role in sensors}
    for role in sensors:
        value = inputs[role.role]
        assert isinstance(value, named(role.icd)), role.role
        holds(value, bus_messages[role.bus].values)


def test_each_actuator_role_s_command_returns_as_its_message_in_the_ticks_gnc_wrote_it(
    roles_runner: FrameRunner,
    roles_contract: tuple[Contract, list[Role]],
    bus_messages: dict[str, Any],
    icd_messages: dict[str, Any],
    holds: Callable[[Any, Mapping[str, Any]], None],
):
    """A tick returns each actuator command GNC wrote as its Basilisk payload, and none it did not.

    The device writes on its first and third steps: those ticks return a fresh
    `messaging.<Name>Payload` per actuator role, each field the ICD field of its name, ignoring
    case, by `fsw.codegen.fields`' rule; the second tick returns nothing.

    Args:
        roles_runner: the frame runner on the rendered mock.
        roles_contract: the rendered contract and the roles.
        bus_messages: a message of each bus struct.
        icd_messages: a value of each ICD struct, the device's commands among them.
        holds: asserts a payload holds values.
    """
    actuators = [role for role in roles_contract[1] if not role.sensor]
    assert actuators
    messages = _sensor_messages(roles_contract[1], bus_messages)

    ticks = [roles_runner.tick(k * NS, messages) for k in (1, 2, 3)]

    assert [sorted(commands) for commands in ticks] == [
        sorted(role.role for role in actuators),
        [],
        sorted(role.role for role in actuators),
    ]
    for commands in (ticks[0], ticks[2]):
        for role in actuators:
            payload = commands[role.role]
            assert type(payload) is payload_type(role.bus), role.role
            holds(payload, icd_messages[role.icd].values)


def test_a_sensor_role_the_vehicle_does_not_have_fails_the_tick_naming_it(
    roles_runner: FrameRunner, roles_contract: tuple[Contract, list[Role]], bus_messages: dict[str, Any]
):
    """A vehicle without a sensor role's message fails the first tick, naming the role.

    Args:
        roles_runner: the frame runner on the rendered mock.
        roles_contract: the rendered contract and the roles.
        bus_messages: a message of each bus struct.
    """
    messages = _sensor_messages(roles_contract[1], bus_messages)
    missing = sorted(messages)[0]
    del messages[missing]

    with pytest.raises(KeyError, match=f"the role {missing},"):
        roles_runner.tick(NS, messages)


def test_a_sensor_role_s_message_of_another_payload_fails_the_tick_naming_both(
    roles_runner: FrameRunner, roles_contract: tuple[Contract, list[Role]], bus_messages: dict[str, Any]
):
    """A role's payload not of the class its bus struct mirrors fails the first tick, naming both.

    Args:
        roles_runner: the frame runner on the rendered mock.
        roles_contract: the rendered contract and the roles.
        bus_messages: a message of each bus struct.
    """
    messages = _sensor_messages(roles_contract[1], bus_messages)
    role = sorted(messages)[0]
    wanted = type(messages[role]).__name__
    assert wanted != "SCStatesMsgPayload"
    messages[role] = payload_type("Bus.SCStatesMsg")()

    with pytest.raises(TypeError, match=f"the role {role}'s message is a SCStatesMsgPayload, .* mirrors {wanted}"):
        roles_runner.tick(NS, messages)


def test_each_boot_checks_the_messages_again_at_its_first_tick(
    roles_runner: FrameRunner, roles_contract: tuple[Contract, list[Role]], bus_messages: dict[str, Any]
):
    """A boot after ticks that passed the check checks the next tick's messages again.

    Args:
        roles_runner: the frame runner on the rendered mock.
        roles_contract: the rendered contract and the roles.
        bus_messages: a message of each bus struct.
    """
    messages = _sensor_messages(roles_contract[1], bus_messages)
    roles_runner.tick(NS, messages)
    missing = sorted(messages)[0]
    del messages[missing]

    roles_runner.boot()

    with pytest.raises(KeyError, match=f"the role {missing},"):
        roles_runner.tick(NS, messages)
