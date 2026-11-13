"""The ground driven tick by tick against a stub link: its waits, its commands and its record.

The stub link holds a toy component's dictionary, generated from FPP alone, and answers and writes
what each test gives it; the tests that fly Leo500 host a toy algorithm for that component.
"""

import json
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

import numpy as np
import pytest
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from gnc_cdh.basilisk import AlgorithmModule
from gnc_cdh.dictionary import Channel, Dictionary
from harness.ground import CommandFailed, Ground

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
    sync command setOffset(offset: Gnc.Vector3, gain: F32)
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
        self.answers: list[tuple[int, int, str | None]] = []
        self.writes: list[tuple[int, int, Any]] = []

    def uplink(self, packet: bytes, context: int) -> None:
        """Keeps the packet and its context.

        Args:
            packet: the command packet.
            context: the ground's number for it.
        """
        self.uplinked.append((packet, context))

    def responses(self) -> list[tuple[int, int, str | None]]:
        """Drains the queued responses.

        Returns:
            `(context, response, reason)` triples.
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


def _ground(link: StubLink, procedure: Callable[[Ground], Coroutine[Any, Any, None]]) -> Ground:
    """A ground running `procedure` on `link`, reset at t = 0 and run at the t = 0 tick.

    Args:
        link: the stub link.
        procedure: the procedure.

    Returns:
        The ground.
    """
    ground = Ground(procedure, link, dict, lambda: None)
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

    with pytest.raises(
        TimeoutError,
        match=r"at t = 2.0 s waiting until the condition at ground_test.py:\d+ holds, by t = 2.0 s",
    ) as raised:
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

    link.answers.append((1, dictionary.responses["OK"], None))
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
            "reason": None,
        }
    ]


def test_the_command_log_holds_array_and_numpy_arguments_as_plain_json(dictionary: Dictionary):
    """An array and a numpy scalar argument are logged as a list and a float, as JSON writes them.

    Args:
        dictionary: the toy's dictionary.
    """
    link = StubLink(dictionary)

    async def procedure(ground: Ground) -> None:
        """Sends `setOffset` with an array and an F32.

        Args:
            ground: the ground running it.
        """
        await ground.send("toy.setOffset", offset=np.array([1.0, 2.0, 3.0]), gain=np.float32(0.25))

    ground = _ground(link, procedure)

    logged = json.loads(json.dumps(ground.command_log))
    assert logged[0]["args"] == {"offset": [1.0, 2.0, 3.0], "gain": 0.25}
    assert type(ground.command_log[0]["args"]["gain"]) is float


def test_consecutive_commands_take_fresh_contexts_and_each_resumes_on_its_own_answer(
    dictionary: Dictionary,
):
    """Two sends uplink under contexts 1 and 2; an answer under another context resumes neither.

    Args:
        dictionary: the toy's dictionary.
    """
    seen = []
    link = StubLink(dictionary)

    async def procedure(ground: Ground) -> None:
        """Sends `setMode` twice, recording the time after each.

        Args:
            ground: the ground running it.
        """
        await ground.send("toy.setMode", mode="fast")
        seen.append(ground.now_s)
        await ground.send("toy.setMode", mode="slow")
        seen.append(ground.now_s)

    ground = _ground(link, procedure)
    link.answers.append((1, dictionary.responses["OK"], None))
    _tick(ground, 1)
    link.answers.append((7, dictionary.responses["OK"], None))
    _tick(ground, 2)
    assert seen == [1.0]
    link.answers.append((2, dictionary.responses["OK"], None))
    _tick(ground, 3)

    assert seen == [1.0, 3.0]
    assert [context for _, context in link.uplinked] == [1, 2]
    assert [(e["context"], e["response"], e["response_t_s"]) for e in ground.command_log] == [
        (1, "OK", 1.0),
        (2, "OK", 3.0),
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
    link.answers.append((1, dictionary.responses["VALIDATION_ERROR"], "not in this mode"))

    with pytest.raises(
        CommandFailed, match="toy.setMode was answered VALIDATION_ERROR: not in this mode"
    ) as raised:
        _tick(ground, 1)

    assert raised.value.reason == "not in this mode"
    assert ground.command_log[0]["response"] == "VALIDATION_ERROR"
    assert ground.command_log[0]["reason"] == "not in this mode"


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

    with pytest.raises(
        TimeoutError, match=r"at t = 1.0 s waiting until toy.setMode is answered, by t = 1.0 s"
    ):
        _tick(ground, 1)


def test_every_write_is_recorded_with_its_tag_in_order_and_tlm_reads_the_latest(
    dictionary: Dictionary,
):
    """Each channel's writes, two at one tag included, land in `tlm/` and `tlm_t/` in order.

    `tlm` reads nothing before the first write, then the channel's latest write. A channel never
    written has no dataset.

    Args:
        dictionary: the toy's dictionary.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Records `toy.offset` at every tick.

        Args:
            ground: the ground running it.
        """
        while True:
            seen.append(ground.tlm("toy.offset"))
            await ground.sleep(1.0)

    link = StubLink(dictionary)
    offset = dictionary.channel("toy.offset").id
    ground = _ground(link, procedure)
    link.writes.append((offset, NS, np.array([1.0, 2.0, 3.0])))
    link.writes.append((offset, NS, np.array([4.0, 5.0, 6.0])))
    _tick(ground, 1, 2)
    link.writes.append((offset, 3 * NS, np.array([7.0, 8.0, 9.0])))
    _tick(ground, 3)

    datasets = ground.telemetry_datasets()

    assert [None if value is None else value.tolist() for value in seen] == [
        None,
        [4.0, 5.0, 6.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 9.0],
    ]
    assert sorted(datasets) == ["tlm/toy.offset", "tlm_t/toy.offset"]
    values, units = datasets["tlm/toy.offset"]
    np.testing.assert_array_equal(values, np.arange(1.0, 10.0).reshape(3, 3))
    assert units == "m"
    times, units = datasets["tlm_t/toy.offset"]
    np.testing.assert_array_equal(times, [1.0, 1.0, 3.0])
    assert units == "s"


def test_a_period_that_is_not_a_whole_multiple_of_the_flight_software_s_is_refused(
    dictionary: Dictionary,
):
    """A ground period that would tick between flight software ticks is refused, naming both.

    Args:
        dictionary: the toy's dictionary.
    """
    link = StubLink(dictionary)

    with pytest.raises(ValueError, match=r"1.5 s is not a whole multiple .* 1.0 s"):
        Ground(_returns, link, dict, lambda: None, period_s=1.5)

    assert Ground(_returns, link, dict, lambda: None, period_s=10.0).period_s == 10.0


async def _returns(ground: Ground) -> None:
    """A procedure that returns at once.

    Args:
        ground: the ground running it.
    """


class Toy:
    """A toy algorithm for the toy component: it writes the time as `offset` every tick."""

    def setMode(self, mode: str) -> dict:
        """Takes the mode and writes it.

        Args:
            mode: the mode's constant name.

        Returns:
            `mode`.
        """
        return {"mode": mode}

    def setOffset(self, offset: np.ndarray, gain: float) -> None:
        """Takes the offset, writing nothing.

        Args:
            offset: (3,) the offset.
            gain: the gain.
        """

    def step(self, t: float) -> dict:
        """Writes the time.

        Args:
            t: s, the tick's time.

        Returns:
            `offset`, `(t, 0, 0)`.
        """
        return {"offset": np.array([t, 0.0, 0.0])}


async def _commands_the_toy(ground: Ground) -> None:
    """Waits 60 s, sets the toy's mode and waits for the toy to report it.

    Args:
        ground: the ground running it.
    """
    await ground.sleep(60.0)
    await ground.send("toy.setMode", mode="fast")
    await ground.until(lambda: ground.tlm("toy.mode") == "fast", timeout_s=5.0)


def test_the_record_is_the_same_whatever_the_ground_s_period_and_whether_it_stops(
    dictionary: Dictionary,
):
    """A ground ticking every second without stopping, every second, or every 10 s, records alike.

    Every dataset of the run file, truth and telemetry, is equal row for row. The ground that does
    not stop last ticks at the run's end; one that stops last ticks where its procedure returned,
    at 61 s on a 1 s ground and at 70 s on a 10 s one, which sees the command's answer then.

    Args:
        dictionary: the toy's dictionary.
    """
    flights = {}
    for period_s, stops in ((1.0, False), (1.0, True), (10.0, True)):
        scenario = Leo500()
        readers = scenario.vehicle.readers()
        fsw = AlgorithmModule(Toy(), readers, instance="toy", dictionary=dictionary)
        stop = scenario.stop_ground if stops else lambda: None
        tracking = scenario.vehicle.tracking()
        ground = Ground(_commands_the_toy, fsw, tracking, stop, period_s=period_s)
        datasets = scenario.run(fsw, {}, duration_s=120.0, ground=ground)
        flights[period_s, stops] = (datasets | ground.telemetry_datasets(), ground.now_s)

    ticking, last_tick_s = flights.pop((1.0, False))
    assert ticking["tlm_t/toy.offset"][0][[0, -1]].tolist() == [1.0, 120.0]
    assert ticking["tlm_t/toy.mode"][0].tolist() == [61.0]
    assert last_tick_s == 120.0
    assert {key: last for key, (_, last) in flights.items()} == {
        (1.0, True): 61.0,
        (10.0, True): 70.0,
    }
    for flown, _ in flights.values():
        assert sorted(flown) == sorted(ticking)
        for name, (values, units) in ticking.items():
            np.testing.assert_array_equal(flown[name][0], values, err_msg=name)
            assert flown[name][1] == units


def test_a_procedure_that_cannot_start_is_kept_whole(dictionary: Dictionary):
    """A procedure that does not take the ground fails at `Reset`, kept whole in `failure`.

    Args:
        dictionary: the toy's dictionary.
    """

    async def procedure() -> None:
        """Takes no ground, so it cannot be started with one."""
        return None

    ground = Ground(procedure, StubLink(dictionary), dict, lambda: None)

    with pytest.raises(TypeError) as raised:
        ground.Reset(0)

    assert ground.failure is raised.value
