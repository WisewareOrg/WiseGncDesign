"""The ground driven tick by tick against a stub edge: its waits, its commands and its record.

The stub edge holds a mock component's dictionary, generated from FPP alone, and answers and writes
what each test gives it; the tests that fly Leo500 host it, as a stub build, in `FswHost`.
"""

import json
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

import numpy as np
import pytest
from wise_dynamics.basilisk import FswHost
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from fsw.codegen.dictionary import Dictionary
from ground.procedures import CommandFailed, Ground

NS = 1_000_000_000
"""ns per s."""


class StubEdge:
    """A radio edge whose responses and writes a test queues, and which keeps what was uplinked.

    Attributes:
        period_s: s, the flight software's period.
        failure: never set; the stub's ticks do not fail.
    """

    period_s = 1.0
    failure = None

    def __init__(self, dictionary: Dictionary) -> None:
        """Holds the dictionary, with nothing queued.

        Args:
            dictionary: the mock's dictionary.
        """
        self.dictionary = dictionary
        self.uplinked: list[tuple[str, dict[str, Any], int]] = []
        self.answers: list[tuple[int, str, str | None]] = []
        self.writes: list[tuple[str, int, Any]] = []

    def uplink(self, name: str, args: dict[str, Any], context: int) -> None:
        """Keeps the command, its arguments and its context.

        Args:
            name: `<instance>.<command>`.
            args: its arguments by parameter name.
            context: the ground's number for it.
        """
        self.uplinked.append((name, args, context))

    def responses(self) -> list[tuple[int, str, str | None]]:
        """Drains the queued responses.

        Returns:
            `(context, response, reason)` triples.
        """
        drained, self.answers = self.answers, []
        return drained

    def telemetry(self) -> list[tuple[str, int, Any]]:
        """Drains the queued writes.

        Returns:
            `(channel name, time tag in ns, value)` triples.
        """
        drained, self.writes = self.writes, []
        return drained

    def values(self, name: str, raws: Sequence[Any]) -> np.ndarray:
        """Packs written values, as the Python build's `GroundLink` does.

        Args:
            name: the channel's name.
            raws: its values.

        Returns:
            As `Channel.pack_many` gives them.
        """
        return self.dictionary.channel(name).pack_many(raws)


@pytest.fixture
def edge(mock_dictionary: Dictionary) -> StubEdge:
    """A stub edge on the mock's dictionary, with nothing queued.

    Args:
        mock_dictionary: the mock's dictionary.

    Returns:
        The edge.
    """
    return StubEdge(mock_dictionary)


def _sends(name: str, **args: Any) -> Callable[[Ground], Coroutine[Any, Any, None]]:
    """A procedure that only sends one command.

    Args:
        name: `<instance>.<command>`.
        **args: its arguments by parameter name.

    Returns:
        The procedure.
    """

    async def procedure(ground: Ground) -> None:
        """Sends the command.

        Args:
            ground: the ground running it.
        """
        await ground.send(name, **args)

    return procedure


def _ground(edge: StubEdge, procedure: Callable[[Ground], Coroutine[Any, Any, None]]) -> Ground:
    """A ground running `procedure` on `edge`, reset at t = 0 and run at the t = 0 tick.

    Args:
        edge: the stub edge.
        procedure: the procedure.

    Returns:
        The ground.
    """
    ground = Ground(procedure, edge, dict, lambda: None)
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


def test_sleep_wakes_at_the_first_tick_at_or_after_its_duration(edge: StubEdge):
    """From t = 0 at 1 s ticks, `sleep(2.5)` resumes at t = 3 s, not before.

    Args:
        edge: the stub edge.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Sleeps 2.5 s, then records the time.

        Args:
            ground: the ground running it.
        """
        await ground.sleep(2.5)
        seen.append(ground.now_s)

    ground = _ground(edge, procedure)
    _tick(ground, 1, 2)
    assert seen == []

    _tick(ground, 3)

    assert seen == [3.0]


def test_until_checks_now_then_each_tick_and_times_out_at_its_deadline(edge: StubEdge):
    """A condition already true passes at once; one never true raises at the tick its time runs out.

    The timeout is kept whole in `failure` and raised from the tick.

    Args:
        edge: the stub edge.
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

    ground = _ground(edge, procedure)
    assert seen == [0.0]
    _tick(ground, 1)

    with pytest.raises(
        TimeoutError,
        match=(
            r"at t = 2.0 s waiting until the condition at procedures_test.py:\d+ holds,"
            r" by t = 2.0 s"
        ),
    ) as raised:
        _tick(ground, 2)

    assert ground.failure is raised.value


def test_send_uplinks_the_command_by_name_and_returns_on_its_ok(edge: StubEdge):
    """The command goes up by name under a fresh context, and its `OK` resumes the procedure.

    The command log holds the command, its arguments as JSON, and its response and time.

    Args:
        edge: the stub edge.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Sends `setMode`, then records the time.

        Args:
            ground: the ground running it.
        """
        await ground.send("mock.setMode", mode="fast")
        seen.append(ground.now_s)

    ground = _ground(edge, procedure)
    assert edge.uplinked == [("mock.setMode", {"mode": "fast"}, 1)]
    _tick(ground, 1)
    assert seen == []

    edge.answers.append((1, "OK", None))
    _tick(ground, 2)

    assert seen == [2.0]
    assert ground.command_log == [
        {
            "t_s": 0.0,
            "name": "mock.setMode",
            "args": {"mode": "fast"},
            "context": 1,
            "response": "OK",
            "response_t_s": 2.0,
            "reason": None,
        }
    ]


def test_send_types_the_arguments_into_the_command_s_fpp_types_and_logs_them_as_plain_json(
    edge: StubEdge,
):
    """The edge gets an F32 as F32 holds it and an array as an array; the log holds plain JSON.

    The log keeps an array as a list and a numpy scalar as a float, as JSON writes them.

    Args:
        edge: the stub edge.
    """
    offset, gain = np.array([1.0, 2.0, 3.0]), np.float32(0.1)
    ground = _ground(edge, _sends("mock.setOffset", offset=offset, gain=gain))

    [(name, args, context)] = edge.uplinked
    assert (name, sorted(args), context) == ("mock.setOffset", ["gain", "offset"], 1)
    assert args["gain"] == float(np.float32(0.1))
    assert isinstance(args["offset"], np.ndarray)
    np.testing.assert_array_equal(args["offset"], [1.0, 2.0, 3.0])
    logged = json.loads(json.dumps(ground.command_log))
    assert logged[0]["args"] == {"offset": [1.0, 2.0, 3.0], "gain": float(np.float32(0.1))}
    assert type(ground.command_log[0]["args"]["gain"]) is float


@pytest.mark.parametrize(
    ("name", "args", "error", "match"),
    [
        ("mock.setMod", {"mode": "fast"}, KeyError, "'mock.setMod'"),
        ("mock.setMode", {"mood": "fast"}, ValueError, r"mock\.setMode takes \['mode'\]"),
    ],
    ids=["unknown-command", "misnamed-argument"],
)
def test_send_refuses_a_command_the_dictionary_cannot_type_before_uplink(
    edge: StubEdge, name: str, args: dict, error: type, match: str
):
    """An unknown command, or arguments that do not fit, raise at `send`, and nothing goes up.

    Args:
        edge: the stub edge.
        name: the command sent.
        args: its arguments.
        error: what `send` raises.
        match: what the error names.
    """
    with pytest.raises(error, match=match):
        _ground(edge, _sends(name, **args))

    assert edge.uplinked == []


def test_consecutive_commands_take_fresh_contexts_and_each_resumes_on_its_own_answer(
    edge: StubEdge,
):
    """Two sends uplink under contexts 1 and 2; an answer under another context resumes neither.

    Args:
        edge: the stub edge.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Sends `setMode` twice, recording the time after each.

        Args:
            ground: the ground running it.
        """
        await ground.send("mock.setMode", mode="fast")
        seen.append(ground.now_s)
        await ground.send("mock.setMode", mode="slow")
        seen.append(ground.now_s)

    ground = _ground(edge, procedure)
    edge.answers.append((1, "OK", None))
    _tick(ground, 1)
    edge.answers.append((7, "OK", None))
    _tick(ground, 2)
    assert seen == [1.0]
    edge.answers.append((2, "OK", None))
    _tick(ground, 3)

    assert seen == [1.0, 3.0]
    assert [context for *_, context in edge.uplinked] == [1, 2]
    assert [(e["context"], e["response"], e["response_t_s"]) for e in ground.command_log] == [
        (1, "OK", 1.0),
        (2, "OK", 3.0),
    ]


def test_a_command_answered_other_than_ok_fails_the_procedure_naming_it(edge: StubEdge):
    """A `VALIDATION_ERROR` raises `CommandFailed` naming the command and the response.

    Args:
        edge: the stub edge.
    """
    ground = _ground(edge, _sends("mock.setMode", mode="slow"))
    edge.answers.append((1, "VALIDATION_ERROR", "not in this mode"))

    with pytest.raises(
        CommandFailed, match="mock.setMode was answered VALIDATION_ERROR: not in this mode"
    ) as raised:
        _tick(ground, 1)

    assert raised.value.reason == "not in this mode"
    assert ground.command_log[0]["response"] == "VALIDATION_ERROR"
    assert ground.command_log[0]["reason"] == "not in this mode"


def test_a_command_never_answered_times_out(edge: StubEdge):
    """With no response, `send` raises at its timeout.

    Args:
        edge: the stub edge.
    """
    ground = _ground(edge, _sends("mock.setMode", timeout_s=1.0, mode="fast"))

    with pytest.raises(
        TimeoutError, match=r"at t = 1.0 s waiting until mock.setMode is answered, by t = 1.0 s"
    ):
        _tick(ground, 1)


def test_every_write_is_recorded_with_its_tag_in_order_and_tlm_reads_the_latest(edge: StubEdge):
    """Each channel's writes, two at one tag included, land in `tlm/` and `tlm_t/` in order.

    `tlm` reads nothing before the first write, then the channel's latest write. A channel never
    written has no dataset.

    Args:
        edge: the stub edge.
    """
    seen = []

    async def procedure(ground: Ground) -> None:
        """Records `mock.offset` at every tick.

        Args:
            ground: the ground running it.
        """
        while True:
            seen.append(ground.tlm("mock.offset"))
            await ground.sleep(1.0)

    ground = _ground(edge, procedure)
    edge.writes.append(("mock.offset", NS, np.array([1.0, 2.0, 3.0])))
    edge.writes.append(("mock.offset", NS, np.array([4.0, 5.0, 6.0])))
    _tick(ground, 1, 2)
    edge.writes.append(("mock.offset", 3 * NS, np.array([7.0, 8.0, 9.0])))
    _tick(ground, 3)

    datasets = ground.telemetry_datasets()

    assert [None if value is None else value.tolist() for value in seen] == [
        None,
        [4.0, 5.0, 6.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 9.0],
    ]
    assert sorted(datasets) == ["tlm/mock.offset", "tlm_t/mock.offset"]
    values, units = datasets["tlm/mock.offset"]
    np.testing.assert_array_equal(values, np.arange(1.0, 10.0).reshape(3, 3))
    assert units == "m"
    times, units = datasets["tlm_t/mock.offset"]
    np.testing.assert_array_equal(times, [1.0, 1.0, 3.0])
    assert units == "s"


def test_a_period_that_is_not_a_whole_multiple_of_the_flight_software_s_is_refused(edge: StubEdge):
    """A ground period that would tick between flight software ticks is refused, naming both.

    Args:
        edge: the stub edge.
    """
    with pytest.raises(ValueError, match=r"1.5 s is not a whole multiple .* 1.0 s"):
        Ground(_returns, edge, dict, lambda: None, period_s=1.5)

    assert Ground(_returns, edge, dict, lambda: None, period_s=10.0).period_s == 10.0


async def _returns(ground: Ground) -> None:
    """A procedure that returns at once.

    Args:
        ground: the ground running it.
    """


class StubBuild(StubEdge):
    """The stub edge as a build `FswHost` hosts, for the flights: it plays the mock component.

    Each tick answers every command uplinked since the last tick `OK`, writes `setMode`'s mode,
    and writes the tick's time as `offset`.
    """

    def __init__(self, dictionary: Dictionary) -> None:
        """Holds the dictionary, with nothing uplinked.

        Args:
            dictionary: the mock's dictionary.
        """
        super().__init__(dictionary)
        self._run = 0

    def boot(self) -> None:
        """Boots with nothing to do."""

    def tick(self, t_ns: int, messages_by_role: dict[str, Any]) -> dict[str, Any]:
        """Runs the commands uplinked since the last tick, then writes the time.

        Args:
            t_ns: ns, the tick's time.
            messages_by_role: the vehicle's messages, unread.

        Returns:
            No actuator command.
        """
        for name, args, context in self.uplinked[self._run :]:
            self.answers.append((context, "OK", None))
            if name == "mock.setMode":
                self.writes.append(("mock.mode", t_ns, args["mode"]))
        self._run = len(self.uplinked)
        self.writes.append(("mock.offset", t_ns, np.array([t_ns / NS, 0.0, 0.0])))
        return {}


async def _commands_the_mock(ground: Ground) -> None:
    """Waits 60 s, sets the mock's mode and waits for the mock to report it.

    Args:
        ground: the ground running it.
    """
    await ground.sleep(60.0)
    await ground.send("mock.setMode", mode="fast")
    await ground.until(lambda: ground.tlm("mock.mode") == "fast", timeout_s=5.0)


def test_the_record_is_the_same_whatever_the_ground_s_period_and_whether_it_stops(
    mock_dictionary: Dictionary,
):
    """A ground ticking every second without stopping, every second, or every 10 s, records alike.

    Every dataset of the run file, truth and telemetry, is equal row for row. The ground that does
    not stop last ticks at the run's end; one that stops last ticks where its procedure returned,
    at 61 s on a 1 s ground and at 70 s on a 10 s one, which sees the command's answer then.

    Args:
        mock_dictionary: the mock's dictionary.
    """
    flights = {}
    for period_s, stops in ((1.0, False), (1.0, True), (10.0, True)):
        scenario = Leo500()
        fsw = StubBuild(mock_dictionary)
        stop = scenario.stop_ground if stops else lambda: None
        tracking = scenario.vehicle.tracking()
        ground = Ground(_commands_the_mock, fsw, tracking, stop, period_s=period_s)
        host = FswHost(fsw, scenario.vehicle)
        datasets = scenario.run(host, {}, duration_s=120.0, ground=ground)
        flights[period_s, stops] = (datasets | ground.telemetry_datasets(), ground.now_s)

    ticking, last_tick_s = flights.pop((1.0, False))
    assert ticking["tlm_t/mock.offset"][0][[0, -1]].tolist() == [1.0, 120.0]
    assert ticking["tlm_t/mock.mode"][0].tolist() == [61.0]
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


def test_tlm_refuses_a_channel_the_dictionary_lacks(edge: StubEdge):
    """A mistyped channel raises `KeyError` naming it, rather than reading `None` forever.

    Args:
        edge: the stub edge.
    """

    async def procedure(ground: Ground) -> None:
        """Reads a misspelled channel.

        Args:
            ground: the ground running it.
        """
        ground.tlm("mock.ofset")

    with pytest.raises(KeyError, match="'mock.ofset'"):
        _ground(edge, procedure)


def test_a_procedure_that_cannot_start_is_kept_whole(edge: StubEdge):
    """A procedure that does not take the ground fails at `Reset`, kept whole in `failure`.

    Args:
        edge: the stub edge.
    """

    async def procedure() -> None:
        """Takes no ground, so it cannot be started with one."""
        return None

    ground = Ground(procedure, edge, dict, lambda: None)

    with pytest.raises(TypeError) as raised:
        ground.Reset(0)

    assert ground.failure is raised.value
