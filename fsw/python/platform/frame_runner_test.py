"""The Python build's frame runner, on a mock GNC sub-topology of two mock algorithms.

The mock's FPP, in `mock/`, is a contract of its own: a source, run every tick, whose sample feeds
a sink, run every second tick, and a command on the source. The mock algorithms are written here,
named as their FPP components; they log what they are given and write what each test needs.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.codegen.deployment import Contract
from fsw.codegen.fpp_types import named
from fsw.python import FrameRunner
from ground.dictionary import Dictionary

MOCK_DIR = Path(__file__).resolve().with_name("mock")

MOCK = Contract((MOCK_DIR / "MockGnc.fpp",), MOCK_DIR / "gnc")
"""The mock's contract: its two algorithms, and its one GNC sub-topology, `MockFrame`."""

CONFIGURATION = "MockFrame"
"""The mock's configuration."""

NS = 1_000_000_000
"""ns per s."""

LOG: list[tuple] = []
"""Each call a mock algorithm received, in order: its instance, what it was, what it was given."""


class Source:
    """The mock that runs first: each step it sends its level times its gain, plus the time."""

    def __init__(self, parameters: Any) -> None:
        """Logs its parameters, and starts at level 0.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        LOG.append(("source", "boot", parameters))
        self._gain = parameters.gain
        self._level = 0.0

    def setLevel(self, level: float) -> Any:
        """Sets the level each later sample carries, refusing a negative one.

        Args:
            level: the level.

        Returns:
            The level, written.

        Raises:
            ValueError: the level is negative.
        """
        if level < 0.0:
            raise ValueError(f"level {level} is negative")
        LOG.append(("source", "setLevel", level))
        self._level = level
        return named("MockGnc.SourceTelemetry")(level=level)

    def step(self, t: float) -> tuple[Any, Any]:
        """Logs the step and sends the sample.

        Args:
            t: s, the time.

        Returns:
            The sample, and the level, written.
        """
        LOG.append(("source", "step", t))
        sample = named("MockGnc.Sample")(value=self._gain * self._level + t)
        return named("MockGnc.SourceOutputs")(sampleOut=sample), named("MockGnc.SourceTelemetry")(
            level=self._level
        )


class Sink:
    """The mock that runs second: it writes the sample it receives, offset."""

    def __init__(self, parameters: Any) -> None:
        """Logs its parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        LOG.append(("sink", "boot", parameters))
        self._offset = parameters.offset

    def step(self, t: float, sample: Any) -> tuple[Any, Any]:
        """Logs the step and the sample it holds, and writes it offset.

        Args:
            t: s, the time.
            sample: the source's latest sample.

        Returns:
            No output, and the sample received, offset.
        """
        LOG.append(("sink", "step", t, sample))
        written = named("MockGnc.SinkTelemetry")(received=sample.value + self._offset)
        return named("MockGnc.SinkOutputs")(), written


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
    assert runner.dictionary.metadata == generated.metadata
    assert generated.metadata["deploymentName"] == f"Py{CONFIGURATION}.Py{CONFIGURATION}"
    assert runner.dictionary.entries("source") == {
        "commands": {
            "GAIN_PRM_SET": [["val", "F64"]],
            "GAIN_PRM_SAVE": [],
            "setLevel": [["level", "F64"]],
        },
        "channels": {"level": ["F64", None]},
    }


def test_boot_builds_each_algorithm_afresh_on_its_record_parameters(runner: FrameRunner):
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

    Taken, refused with its reason, a parameter's set command and an unknown name are each
    answered as F´ answers them.

    Args:
        runner: the frame runner.
    """
    runner.uplink("source.setLevel", {"level": 1.5}, 7)
    runner.uplink("source.setLevel", {"level": -1.0}, 8)
    runner.uplink("source.GAIN_PRM_SET", {"val": 1.0}, 9)
    runner.uplink("source.notACommand", {}, 10)
    assert runner.responses() == []

    runner.tick(NS // 2, {})

    assert [(instance, kind) for instance, kind, *_ in LOG][:2] == [
        ("source", "setLevel"),
        ("source", "step"),
    ]
    assert runner.responses() == [
        (7, "OK", None),
        (8, "VALIDATION_ERROR", "level -1.0 is negative"),
        (9, "INVALID_OPCODE", None),
        (10, "INVALID_OPCODE", None),
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
    np.testing.assert_array_equal(
        runner.values("sink.received", [raw]), [2.5 * 2.0 + t_ns / NS + 0.25]
    )
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
