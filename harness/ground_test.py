"""The ground driven tick by tick against a stub link: its waits, its commands and its record.

The stub link holds a toy component's dictionary, generated from FPP alone, and answers and writes
what each test gives it.
"""

from collections.abc import Callable, Coroutine, Sequence
from typing import Any

import numpy as np
import pytest
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from gnc_algorithms.imu_dead_reckoning import dead_reckoner
from gnc_cdh.dictionary import Channel, Dictionary
from harness.ground import CommandFailed, Ground
from scenarios.leo import leo500

NS = 1_000_000_000
"""ns per s."""

TOY = """\
module Toy {

  enum Mode {
    slow
    fast
  }

  passive component Toy {
    sync command setMode(mode: Mode)
    telemetry mode: Mode
    telemetry offset: Gnc.Vector3 format "{} m"
    time get port timeCaller
    telemetry port tlmOut
    command reg port cmdRegOut
    command recv port cmdIn
    command resp port cmdResponseOut
  }

}
"""


@pytest.fixture(scope="module")
def dictionary(tmp_path_factory: pytest.TempPathFactory) -> Dictionary:
    """The toy's dictionary, instanced as `toy`.

    Args:
        tmp_path_factory: where the toy's model is written.

    Returns:
        The dictionary.
    """
    model = tmp_path_factory.mktemp("toy") / "Toy.fpp"
    model.write_text(TOY)
    return Dictionary.from_component([model], "Toy.Toy", instance="toy")


class StubLink:
    """A link whose responses and writes a test queues, and which keeps what was uplinked.

    Attributes:
        period_s: s, the flight software's period.
        failure: never set; the stub's ticks do not fail.
    """

    period_s = 1.0
    failure = None

    def __init__(self, dictionary: Dictionary) -> None:
        """Holds the dictionary, with nothing queued.

        Args:
            dictionary: the toy's dictionary.
        """
        self.dictionary = dictionary
        self.uplinked: list[tuple[bytes, int]] = []
        self.answers: list[tuple[int, int]] = []
        self.writes: list[tuple[int, int, Any]] = []
        self.stops = 0

    def stop(self) -> None:
        """Counts a call, standing in for the scenario stopping the ground's task."""
        self.stops += 1

    def uplink(self, packet: bytes, context: int) -> None:
        """Keeps the packet and its context.

        Args:
            packet: the command packet.
            context: the ground's number for it.
        """
        self.uplinked.append((packet, context))

    def responses(self) -> list[tuple[int, int]]:
        """Drains the queued responses.

        Returns:
            `(context, response)` pairs.
        """
        drained, self.answers = self.answers, []
        return drained

    def telemetry(self) -> list[tuple[int, int, Any]]:
        """Drains the queued writes.

        Returns:
            `(channel ID, time tag in ns, value)` triples.
        """
        drained, self.writes = self.writes, []
        return drained

    def values(self, channel: Channel, payloads: Sequence[Any]) -> np.ndarray:
        """Packs written values, as the Python host does.

        Args:
            channel: the channel.
            payloads: its values.

        Returns:
            As `Channel.pack_many` gives them.
        """
        return channel.pack_many(payloads)

    def write(self, name: str, t_ns: int, value: Any) -> None:
        """Queues one write.

        Args:
            name: `<instance>.<channel>`.
            t_ns: ns, its time tag.
            value: the value written.
        """
        self.writes.append((self.dictionary.channel(name).id, t_ns, value))


def _ground(link: StubLink, procedure: Callable[[Ground], Coroutine[Any, Any, None]]) -> Ground:
    """A ground running `procedure` on `link`, reset at t = 0 and run at the t = 0 tick.

    Args:
        link: the stub link.
        procedure: the procedure.

    Returns:
        The ground.
    """
    ground = Ground(procedure, link, lambda: {"r_N": np.array([1.0, 2.0, 3.0])}, link.stop)
    ground.Reset(0)
    ground.UpdateState(0)
    return ground


def _tick(ground: Ground, *seconds: int) -> None:
    """Runs the ground at each whole second given.

    Args:
        ground: the ground.
        *seconds: s, the ticks' times.
    """
    for t in seconds:
        ground.UpdateState(t * NS)


def test_sleep_wakes_at_the_first_tick_at_or_after_its_duration(dictionary: Dictionary):
    """From t = 0 at 1 s ticks, `sleep(2.5)` resumes at t = 3 s, not before.

    Args:
        dictionary: the toy's dictionary.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Sleeps 2.5 s, then records the time.

        Args:
            ground: the ground running it.
        """
        await ground.sleep(2.5)
        seen.append(ground.now_s)

    ground = _ground(StubLink(dictionary), procedure)
    _tick(ground, 1, 2)
    assert seen == []

    _tick(ground, 3)

    assert seen == [3.0]


def test_until_checks_now_then_each_tick_and_times_out_at_its_deadline(dictionary: Dictionary):
    """A condition already true passes at once; one never true raises at the tick its time runs out.

    The timeout is kept whole in `failure` and raised from the tick.

    Args:
        dictionary: the toy's dictionary.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Waits on a true condition, records the time, then waits on a false one.

        Args:
            ground: the ground running it.
        """
        await ground.until(lambda: True, timeout_s=0.0)
        seen.append(ground.now_s)
        await ground.until(lambda: False, timeout_s=2.0)

    ground = _ground(StubLink(dictionary), procedure)
    assert seen == [0.0]
    _tick(ground, 1)

    with pytest.raises(TimeoutError, match=r"within 2.0 s, at t = 2.0 s") as raised:
        _tick(ground, 2)

    assert ground.failure is raised.value


def test_send_uplinks_the_encoded_command_and_returns_on_its_ok(dictionary: Dictionary):
    """The packet is the dictionary's, under a fresh context, and its `OK` resumes the procedure.

    The command log holds the command, its arguments as JSON, and its response and time.

    Args:
        dictionary: the toy's dictionary.
    """
    seen = []
    link = StubLink(dictionary)

    async def procedure(ground: Ground) -> None:
        """Sends `setMode`, then records the time.

        Args:
            ground: the ground running it.
        """
        await ground.send("toy.setMode", mode="fast")
        seen.append(ground.now_s)

    ground = _ground(link, procedure)
    assert link.uplinked == [(dictionary.encode_command("toy.setMode", {"mode": "fast"}), 1)]
    _tick(ground, 1)
    assert seen == []

    link.answers.append((1, dictionary.responses["OK"]))
    _tick(ground, 2)

    assert seen == [2.0]
    assert ground.command_log == [
        {
            "t_s": 0.0,
            "name": "toy.setMode",
            "args": {"mode": "fast"},
            "context": 1,
            "response": "OK",
            "response_t_s": 2.0,
        }
    ]


def test_a_command_answered_other_than_ok_fails_the_procedure_naming_it(dictionary: Dictionary):
    """A `VALIDATION_ERROR` raises `CommandFailed` naming the command and the response.

    Args:
        dictionary: the toy's dictionary.
    """
    link = StubLink(dictionary)

    async def procedure(ground: Ground) -> None:
        """Sends `setMode`.

        Args:
            ground: the ground running it.
        """
        await ground.send("toy.setMode", mode="slow")

    ground = _ground(link, procedure)
    link.answers.append((1, dictionary.responses["VALIDATION_ERROR"]))

    with pytest.raises(CommandFailed, match="toy.setMode was answered VALIDATION_ERROR"):
        _tick(ground, 1)

    assert ground.command_log[0]["response"] == "VALIDATION_ERROR"


def test_a_command_never_answered_times_out(dictionary: Dictionary):
    """With no response, `send` raises at its timeout.

    Args:
        dictionary: the toy's dictionary.
    """

    async def procedure(ground: Ground) -> None:
        """Sends `setMode`, waiting 1 s for its response.

        Args:
            ground: the ground running it.
        """
        await ground.send("toy.setMode", timeout_s=1.0, mode="fast")

    ground = _ground(StubLink(dictionary), procedure)

    with pytest.raises(TimeoutError, match="at t = 1.0 s"):
        _tick(ground, 1)


def test_tlm_is_none_until_written_then_the_latest_write(dictionary: Dictionary):
    """A watcher reads nothing before the first write, then the channel's latest write.

    Args:
        dictionary: the toy's dictionary.
    """
    seen = []
    link = StubLink(dictionary)

    async def procedure(ground: Ground) -> None:
        """Records `toy.mode` at every tick.

        Args:
            ground: the ground running it.
        """
        while True:
            seen.append(ground.tlm("toy.mode"))
            await ground.sleep(1.0)

    ground = _ground(link, procedure)
    link.write("toy.mode", NS, "slow")
    link.write("toy.mode", NS, "fast")
    _tick(ground, 1)

    assert seen == [None, "fast"]


def test_every_write_is_recorded_with_its_tag_in_order(dictionary: Dictionary):
    """Each channel's writes, two at one tag included, land in `tlm/` and `tlm_t/` in order.

    A channel never written has no dataset.

    Args:
        dictionary: the toy's dictionary.
    """

    async def procedure(ground: Ground) -> None:
        """Waits past the test's ticks.

        Args:
            ground: the ground running it.
        """
        await ground.sleep(10.0)

    link = StubLink(dictionary)
    ground = _ground(link, procedure)
    link.write("toy.offset", NS, np.array([1.0, 2.0, 3.0]))
    link.write("toy.offset", NS, np.array([4.0, 5.0, 6.0]))
    _tick(ground, 1, 2)
    link.write("toy.offset", 3 * NS, np.array([7.0, 8.0, 9.0]))
    _tick(ground, 3)

    datasets = ground.telemetry_datasets()

    assert sorted(datasets) == ["tlm/toy.offset", "tlm_t/toy.offset"]
    values, units = datasets["tlm/toy.offset"]
    np.testing.assert_array_equal(values, np.arange(1.0, 10.0).reshape(3, 3))
    assert units == "m"
    times, units = datasets["tlm_t/toy.offset"]
    np.testing.assert_array_equal(times, [1.0, 1.0, 3.0])
    assert units == "s"


def test_the_ground_stops_once_its_procedure_returns_and_still_records_later_writes(
    dictionary: Dictionary,
):
    """A returned procedure stops the ground once; writes made after it still reach the record.

    The writes the link holds when the run ends are taken by `telemetry_datasets`.

    Args:
        dictionary: the toy's dictionary.
    """

    async def procedure(ground: Ground) -> None:
        """Waits one tick, then returns.

        Args:
            ground: the ground running it.
        """
        await ground.sleep(1.0)

    link = StubLink(dictionary)
    ground = _ground(link, procedure)
    assert link.stops == 0
    _tick(ground, 1)
    assert link.stops == 1
    link.write("toy.mode", 2 * NS, "fast")
    link.write("toy.mode", 3 * NS, "slow")

    datasets = ground.telemetry_datasets()

    assert datasets["tlm/toy.mode"][0].tolist() == ["fast", "slow"]
    np.testing.assert_array_equal(datasets["tlm_t/toy.mode"][0], [2.0, 3.0])


@pytest.mark.parametrize("period_s", [0.5, 1.5])
def test_a_period_that_is_not_a_whole_multiple_of_the_flight_software_s_is_refused(
    dictionary: Dictionary, period_s: float
):
    """A ground period that would tick between flight software ticks is refused, naming both.

    Args:
        dictionary: the toy's dictionary.
        period_s: s, the ground's period, against the stub's 1 s.
    """
    link = StubLink(dictionary)

    with pytest.raises(ValueError, match=rf"{period_s} s is not a whole multiple .* 1.0 s"):
        Ground(_returns, link, dict, link.stop, period_s=period_s)

    assert Ground(_returns, link, dict, link.stop, period_s=10.0).period_s == 10.0


async def _returns(ground: Ground) -> None:
    """A procedure that returns at once.

    Args:
        ground: the ground running it.
    """


def _flown(period_s: float, stops: bool) -> dict[str, tuple[np.ndarray, str]]:
    """The datasets of 120 s of nominal Leo500 flown by the dead reckoner under `leo500`.

    Args:
        period_s: s, the ground's period.
        stops: whether the ground's task stops once the procedure returns.

    Returns:
        The run's datasets and the ground's telemetry datasets.
    """
    scenario = Leo500()
    fsw = dead_reckoner(scenario)
    stop = scenario.stop_ground if stops else lambda: None
    ground = Ground(leo500, fsw, scenario.vehicle.tracking(), stop, period_s=period_s)
    datasets = scenario.run(fsw, {}, duration_s=120.0, ground=ground)
    return datasets | ground.telemetry_datasets()


def test_the_record_is_the_same_whatever_the_ground_s_period_and_whether_it_stops():
    """A ground ticking every second without stopping, every second, or every 10 s, records alike.

    Every dataset of the run file, truth and telemetry, is equal row for row.
    """
    ticking = _flown(1.0, stops=False)
    assert ticking["tlm_t/nav.bodyEciPos"][0][[0, -1]].tolist() == [61.0, 120.0]

    for flown in (_flown(1.0, stops=True), _flown(10.0, stops=True)):
        assert sorted(flown) == sorted(ticking)
        for name, (values, units) in ticking.items():
            np.testing.assert_array_equal(flown[name][0], values, err_msg=name)
            assert flown[name][1] == units


def test_truth_reads_the_tracking_stand_in_now(dictionary: Dictionary):
    """`truth()` is what the ground's tracking function gives when the procedure asks.

    Args:
        dictionary: the toy's dictionary.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Records the truth.

        Args:
            ground: the ground running it.
        """
        seen.append(ground.truth())

    _ground(StubLink(dictionary), procedure)

    np.testing.assert_array_equal(seen[0]["r_N"], [1.0, 2.0, 3.0])


def test_the_ground_runs_at_the_link_s_period(dictionary: Dictionary):
    """The ground's period is the flight software's.

    Args:
        dictionary: the toy's dictionary.
    """
    link = StubLink(dictionary)
    link.period_s = 0.5

    async def procedure(ground: Ground) -> None:
        """Returns at once.

        Args:
            ground: the ground running it.
        """
        return None

    assert Ground(procedure, link, dict, link.stop).period_s == 0.5


def test_a_procedure_that_cannot_start_is_kept_whole(dictionary: Dictionary):
    """A procedure that does not take the ground fails at `Reset`, kept whole in `failure`.

    Args:
        dictionary: the toy's dictionary.
    """

    async def procedure() -> None:
        """Takes no ground, so it cannot be started with one."""
        return None

    link = StubLink(dictionary)
    ground = Ground(procedure, link, dict, link.stop)

    with pytest.raises(TypeError) as raised:
        ground.Reset(0)

    assert ground.failure is raised.value
