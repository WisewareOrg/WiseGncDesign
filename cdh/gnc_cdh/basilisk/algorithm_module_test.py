"""`AlgorithmModule` driven directly, on the link.

It hosts stub algorithms, wired by their names, on standalone Basilisk messages, as the instance
`toy` of a toy component whose dictionary is generated from FPP alone.
"""

import numpy as np
import pytest
from Basilisk.architecture import messaging
from Basilisk.utilities import SimulationBaseClass, macros

from gnc_cdh.basilisk import AlgorithmModule
from gnc_cdh.dictionary import Dictionary

ONE_SECOND_NS = 1_000_000_000

STEPPED = np.array([1.0, 2.0, 3.0])
"""What the stub writes as `offset` at t = 1 s; at time t it writes `t * STEPPED`."""

TOY = """\
module Toy {

  enum Mode {
    slow
    fast
  }

  passive component Toy {
    sync command setGain(gain: F32, mode: Mode)
    telemetry gain: F32
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


class StubAlgorithm:
    """A stub algorithm that records what reaches it.

    It reads `AngVelPlatform` from an IMU message and `sigma_BN` from a navigation message, writes
    `offset` as `t * STEPPED` each step, and takes `setGain`, refusing a negative gain.
    """

    def __init__(self) -> None:
        """Starts with nothing recorded."""
        self.steps: list[dict] = []
        self.commands: list[dict] = []

    def setGain(self, gain: float, mode: str) -> dict:
        """Records the command's arguments and writes them.

        Args:
            gain: the gain, as F32 decodes it.
            mode: the mode's constant name.

        Returns:
            `gain` and `mode`.

        Raises:
            ValueError: the gain is negative.
        """
        if gain < 0.0:
            raise ValueError("a negative gain")
        self.commands.append({"gain": gain, "mode": mode})
        return {"gain": gain, "mode": mode}

    def step(self, t: float, AngVelPlatform: np.ndarray, sigma_BN: np.ndarray) -> dict:
        """Records the step's inputs and writes `offset`.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.
            sigma_BN: (3,) MRP, read from the navigation message.

        Returns:
            `offset`, `t * STEPPED`.
        """
        self.steps.append({"t": t, "AngVelPlatform": AngVelPlatform, "sigma_BN": sigma_BN})
        return {"offset": t * STEPPED}


class InPlace(StubAlgorithm):
    """A stub that writes `offset` from one array it changes in place each step."""

    def __init__(self) -> None:
        """Starts as `StubAlgorithm` does, plus the array it writes."""
        super().__init__()
        self.offset = np.zeros(3)

    def step(self, t: float, AngVelPlatform: np.ndarray, sigma_BN: np.ndarray) -> dict:
        """Steps `offset` in place and writes it.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.
            sigma_BN: (3,) MRP, read from the navigation message.

        Returns:
            `offset`, the array the stub holds.
        """
        self.offset[:] = t * STEPPED
        return {"offset": self.offset}


class Misspelled(StubAlgorithm):
    """A stub whose `step` writes a channel the dictionary does not have."""

    def step(self, t: float, AngVelPlatform: np.ndarray, sigma_BN: np.ndarray) -> dict:
        """Writes `ofset`.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.
            sigma_BN: (3,) MRP, read from the navigation message.

        Returns:
            `ofset`.
        """
        return {"ofset": t * STEPPED}


class Broken(StubAlgorithm):
    """A stub whose `step` has a bug."""

    def step(self, t: float, AngVelPlatform: np.ndarray, sigma_BN: np.ndarray) -> None:
        """Fails as a bug in an algorithm does.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.
            sigma_BN: (3,) MRP, read from the navigation message.

        Raises:
            ZeroDivisionError: always.
        """
        raise ZeroDivisionError("the step's own bug")


class BrokenHandler(StubAlgorithm):
    """A stub whose `setGain` has a bug."""

    def setGain(self, gain: float, mode: str) -> None:
        """Fails as a bug in a handler does.

        Args:
            gain: the gain.
            mode: the mode.

        Raises:
            KeyError: always.
        """
        raise KeyError("the handler's own bug")


class MisspelledHandler(StubAlgorithm):
    """A stub whose `setGain` writes a channel the dictionary does not have."""

    def setGain(self, gain: float, mode: str) -> dict:
        """Writes `gian`.

        Args:
            gain: the gain.
            mode: the mode.

        Returns:
            `gian`.
        """
        return {"gian": gain}


class NoHandler:
    """A stub with no method for the toy's command."""

    def step(self, t: float, AngVelPlatform: np.ndarray) -> dict:
        """Writes nothing.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.

        Returns:
            Nothing.
        """
        return {}


class MisnamedParameter(NoHandler):
    """A stub whose handler names a parameter other than the command's."""

    def setGain(self, gain: float, mod: str) -> None:
        """Takes the command under a misspelled parameter.

        Args:
            gain: the gain.
            mod: the mode, misspelled.
        """


class UnreadKeyword(NoHandler):
    """A stub whose `step` asks for a field no input's message carries."""

    def setGain(self, gain: float, mode: str) -> None:
        """Takes the command.

        Args:
            gain: the gain.
            mode: the mode.
        """

    def step(self, t: float, AngVelPlatfrom: np.ndarray) -> dict:
        """Asks for a misspelled field, which construction refuses before any step.

        Args:
            t: s, the step's time.
            AngVelPlatfrom: (3,) rad/s, a field no input's message carries.

        Returns:
            Nothing.
        """
        return {}


def _imu_message(angvel: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> messaging.IMUSensorMsg:
    """A written IMU message.

    Args:
        angvel: (3,) rad/s, its `AngVelPlatform`.

    Returns:
        The `IMUSensorMsg`, written at t = 0.
    """
    msg = messaging.IMUSensorMsg()
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = list(angvel)
    msg.write(payload, 0, 0)
    return msg


def _nav_message(sigma: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> messaging.NavAttMsg:
    """A written navigation attitude message.

    Args:
        sigma: (3,) MRP, its `sigma_BN`.

    Returns:
        The `NavAttMsg`, written at t = 0.
    """
    msg = messaging.NavAttMsg()
    payload = messaging.NavAttMsgPayload()
    payload.sigma_BN = list(sigma)
    msg.write(payload, 0, 0)
    return msg


def _readers() -> dict:
    """An unsubscribed IMU and navigation reader.

    Returns:
        `imu`, an `IMUSensorMsgReader`, and `nav`, a `NavAttMsgReader`, by role.
    """
    return {"imu": messaging.IMUSensorMsgReader(), "nav": messaging.NavAttMsgReader()}


def _module(dictionary: Dictionary, algorithm: object | None = None) -> AlgorithmModule:
    """A stub algorithm hosted on `_readers()` as `toy`.

    Args:
        dictionary: the toy's dictionary.
        algorithm: the algorithm to host; a fresh `StubAlgorithm` when `None`.

    Returns:
        The `AlgorithmModule`.
    """
    algorithm = StubAlgorithm() if algorithm is None else algorithm
    return AlgorithmModule(algorithm, _readers(), instance="toy", dictionary=dictionary)


def _subscribed(
    module: AlgorithmModule,
    angvel: tuple[float, float, float] = (1.0, 2.0, 3.0),
    sigma: tuple[float, float, float] = (0.4, 0.5, 0.6),
) -> tuple[messaging.IMUSensorMsg, messaging.NavAttMsg]:
    """Subscribes `module`'s `imu` and `nav` readers to written messages.

    Args:
        module: the host module whose readers subscribe.
        angvel: (3,) rad/s, the IMU message's `AngVelPlatform`.
        sigma: (3,) MRP, the navigation message's `sigma_BN`.

    Returns:
        The two messages, returned so they outlive the call.
    """
    imu, nav = _imu_message(angvel), _nav_message(sigma)
    module.inputs["imu"].subscribeTo(imu)
    module.inputs["nav"].subscribeTo(nav)
    return imu, nav


def _writes(module: AlgorithmModule) -> list[tuple[str, int, object]]:
    """Drains the module's telemetry, named and packed.

    Args:
        module: the host.

    Returns:
        Each write's channel name, time tag in ns and packed value, in the order written.
    """
    channels = module.dictionary.channels_by_id
    return [
        (channels[i].name, t_ns, module.values(channels[i], [value])[0])
        for i, t_ns, value in module.telemetry()
    ]


def _send(module: AlgorithmModule, packet: bytes, context: int = 1) -> None:
    """Uplinks a packet and runs the next tick, at 1 s.

    Args:
        module: the host, reset at t = 0.
        packet: the command packet.
        context: the ground's number for it.
    """
    module.uplink(packet, context)
    module.UpdateState(ONE_SECOND_NS)


def test_each_step_keyword_is_read_from_the_message_carrying_that_field(dictionary: Dictionary):
    """A step receives `t` in s and each keyword from the input whose message has that field.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    step = module.algorithm.steps[-1]
    assert step["t"] == 1.0
    np.testing.assert_array_equal(step["AngVelPlatform"], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(step["sigma_BN"], [0.4, 0.5, 0.6])


def test_a_command_runs_before_the_next_step_decoded_as_f_prime_hands_it_and_answers_ok(
    dictionary: Dictionary,
):
    """The handler gets the F32 as F32 holds it and the enum by name, then `OK` under the context.

    Its writes come first in the tick, tagged with the tick's time, before the step's.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)
    _messages = _subscribed(module)
    module.Reset(0)

    _send(module, dictionary.encode_command("toy.setGain", {"gain": 0.1, "mode": "fast"}), 7)

    gain = float(np.float32(0.1))
    assert module.algorithm.commands == [{"gain": gain, "mode": "fast"}]
    assert module.responses() == [(7, dictionary.responses["OK"], None)]
    assert module.responses() == []
    writes = _writes(module)
    assert [(name, t_ns) for name, t_ns, _ in writes] == [
        ("toy.gain", ONE_SECOND_NS),
        ("toy.mode", ONE_SECOND_NS),
        ("toy.offset", ONE_SECOND_NS),
    ]
    assert writes[0][2] == gain
    assert writes[1][2] == "fast"
    np.testing.assert_array_equal(writes[2][2], STEPPED)
    assert module.telemetry() == []


def test_a_handler_that_raises_value_error_answers_validation_error_and_writes_nothing(
    dictionary: Dictionary,
):
    """A handler refusing its arguments answers `VALIDATION_ERROR` with its message as the reason.

    The tick goes on to the step.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)
    _messages = _subscribed(module)
    module.Reset(0)

    _send(module, dictionary.encode_command("toy.setGain", {"gain": -1.0, "mode": "slow"}))

    assert module.responses() == [(1, dictionary.responses["VALIDATION_ERROR"], "a negative gain")]
    assert [name for name, _, _ in _writes(module)] == ["toy.offset"]


@pytest.mark.parametrize(
    ("cut", "response"),
    [(slice(0, 4), "VALIDATION_ERROR"), (slice(0, -1), "FORMAT_ERROR")],
    ids=["truncated-head", "short-arguments"],
)
def test_a_malformed_packet_earns_the_dictionary_s_response_and_runs_nothing(
    dictionary: Dictionary, cut: slice, response: str
):
    """A packet the dictionary cannot decode is answered as F´ answers it, and no handler runs.

    Args:
        dictionary: the toy's dictionary.
        cut: the part of a good packet sent.
        response: the `Fw.CmdResponse` it earns.
    """
    module = _module(dictionary)
    _messages = _subscribed(module)
    module.Reset(0)
    packet = dictionary.encode_command("toy.setGain", {"gain": 0.1, "mode": "fast"})

    _send(module, packet[cut])

    assert module.responses() == [(1, dictionary.responses[response], None)]
    assert module.algorithm.commands == []


def test_a_handler_s_bug_fails_the_tick_kept_whole_and_is_not_answered(dictionary: Dictionary):
    """A handler raising anything but `ValueError` fails its tick as itself, with no response.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary, BrokenHandler())
    _messages = _subscribed(module)
    module.Reset(0)

    with pytest.raises(KeyError, match="the handler's own bug") as raised:
        _send(module, dictionary.encode_command("toy.setGain", {"gain": 0.1, "mode": "fast"}))

    assert module.failure is raised.value
    assert module.responses() == []


def test_a_handler_s_write_to_a_channel_the_dictionary_lacks_fails_naming_it(
    dictionary: Dictionary,
):
    """A handler's write of `gian` raises at its tick, as a step's would.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary, MisspelledHandler())
    _messages = _subscribed(module)
    module.Reset(0)

    with pytest.raises(ValueError, match=r"toy\.gian is not a channel") as raised:
        _send(module, dictionary.encode_command("toy.setGain", {"gain": 0.1, "mode": "fast"}))

    assert module.failure is raised.value


def test_a_write_to_a_channel_the_dictionary_lacks_fails_on_its_tick_naming_it(
    dictionary: Dictionary,
):
    """The step's write of `ofset` raises at that tick, and the exception is kept whole.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary, Misspelled())
    _messages = _subscribed(module)
    module.Reset(0)

    with pytest.raises(ValueError, match=r"toy\.ofset is not a channel") as raised:
        module.UpdateState(ONE_SECOND_NS)

    assert module.failure is raised.value


def test_an_exception_in_the_algorithm_is_kept_whole_and_raised_from_the_tick(
    dictionary: Dictionary,
):
    """A bug in `step` reaches the caller as itself, and `failure` holds the same exception.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary, Broken())
    _messages = _subscribed(module)
    module.Reset(0)

    with pytest.raises(ZeroDivisionError, match="the step's own bug") as raised:
        module.UpdateState(ONE_SECOND_NS)

    assert module.failure is raised.value


def test_a_value_that_does_not_fit_its_channel_fails_when_packed_naming_it(
    dictionary: Dictionary,
):
    """A write is held to its channel's type when the batch is packed, not on its tick.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)

    with pytest.raises(ValueError, match="channel toy.mode"):
        module.values(dictionary.channel("toy.mode"), ["fast", "medium"])


def test_each_write_keeps_the_value_written_when_the_algorithm_changes_its_array_in_place(
    dictionary: Dictionary,
):
    """An algorithm that steps by mutating one array still leaves each tick's value in the log.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary, InPlace())
    _messages = _subscribed(module)
    module.Reset(0)

    module.UpdateState(ONE_SECOND_NS)
    module.UpdateState(2 * ONE_SECOND_NS)

    np.testing.assert_array_equal([value for *_, value in _writes(module)], [STEPPED, 2 * STEPPED])


def test_the_tick_is_gated_on_the_host_s_own_last_tick(dictionary: Dictionary):
    """The call at the reset time and a repeated tick run nothing; each later tick steps once.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(0)
    assert module.algorithm.steps == []

    module.UpdateState(ONE_SECOND_NS)
    module.UpdateState(ONE_SECOND_NS)
    assert [step["t"] for step in module.algorithm.steps] == [1.0]


@pytest.mark.parametrize(
    ("algorithm", "message"),
    [
        (NoHandler(), r"toy\.setGain takes \['gain', 'mode'\]; the algorithm has no such method"),
        (MisnamedParameter(), r"toy\.setGain takes \['gain', 'mode'\]; .* \['gain', 'mod'\]"),
    ],
    ids=["no-handler", "misnamed-parameter"],
)
def test_construction_refuses_a_command_the_algorithm_does_not_handle_as_declared(
    dictionary: Dictionary, algorithm: object, message: str
):
    """Each command of the instance must be a method with exactly the command's parameters.

    Args:
        dictionary: the toy's dictionary.
        algorithm: the stub missing or misdeclaring `setGain`.
        message: what the refusal says.
    """
    with pytest.raises(ValueError, match=message):
        _module(dictionary, algorithm)


def test_construction_names_a_keyword_no_input_carries(dictionary: Dictionary):
    """A `step` keyword that no input's message has as a field is refused by name.

    Args:
        dictionary: the toy's dictionary.
    """
    with pytest.raises(ValueError, match=r"'AngVelPlatfrom' is carried by 0 inputs"):
        _module(dictionary, UnreadKeyword())


def test_construction_names_a_keyword_two_inputs_carry(dictionary: Dictionary):
    """A `step` keyword that two inputs' messages both carry is refused by name.

    Args:
        dictionary: the toy's dictionary.
    """
    readers = {
        "imu_a": messaging.IMUSensorMsgReader(),
        "imu_b": messaging.IMUSensorMsgReader(),
        "nav": messaging.NavAttMsgReader(),
    }
    with pytest.raises(ValueError, match=r"'AngVelPlatform' is carried by 2 inputs"):
        AlgorithmModule(StubAlgorithm(), readers, instance="toy", dictionary=dictionary)


def test_the_input_table_is_read_only(dictionary: Dictionary):
    """The input readers cannot be replaced.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)

    with pytest.raises(TypeError):
        module.inputs["extra"] = messaging.NavAttMsgReader()


def test_reset_names_an_unsubscribed_input_and_keeps_the_exception(dictionary: Dictionary):
    """`Reset` names the input reader that is not subscribed, the exception kept in `failure`.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)
    imu = _imu_message()
    module.inputs["imu"].subscribeTo(imu)

    with pytest.raises(RuntimeError, match=r"\['nav'\] are not subscribed") as raised:
        module.Reset(0)

    assert module.failure is raised.value


def test_a_step_names_an_input_never_written(dictionary: Dictionary):
    """A step names the subscribed input that has never been written.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)
    imu, nav = _imu_message(), messaging.NavAttMsg()  # nav subscribed, never written
    module.inputs["imu"].subscribeTo(imu)
    module.inputs["nav"].subscribeTo(nav)
    module.Reset(0)

    with pytest.raises(RuntimeError, match=r"\['nav'\] have not been written"):
        module.UpdateState(ONE_SECOND_NS)


def test_a_task_at_the_module_period_steps_and_tags_each_write_at_whole_seconds(
    dictionary: Dictionary,
):
    """Run 3.5 s in a task every `period_s`, the module writes at 1, 2 and 3 s only.

    Args:
        dictionary: the toy's dictionary.
    """
    module = _module(dictionary)
    _messages = _subscribed(module)
    sim = SimulationBaseClass.SimBaseClass()
    sim.CreateNewProcess("process").addTask(
        sim.CreateNewTask("task", macros.sec2nano(module.period_s))
    )
    sim.AddModelToTask("task", module)

    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(3.5))
    sim.ExecuteSimulation()

    writes = _writes(module)
    assert [t_ns for _, t_ns, _ in writes] == [ONE_SECOND_NS * k for k in (1, 2, 3)]
    np.testing.assert_array_equal(
        [value for *_, value in writes], [STEPPED, 2 * STEPPED, 3 * STEPPED]
    )


def test_the_build_names_the_host(dictionary: Dictionary):
    """`build` is exactly the host's name.

    Args:
        dictionary: the toy's dictionary.
    """
    assert _module(dictionary).build == {"host": "gnc_cdh.basilisk.AlgorithmModule"}
