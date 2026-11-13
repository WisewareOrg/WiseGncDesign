"""`AlgorithmModule` driven directly.

It hosts stub algorithms, wired by their names, on standalone Basilisk messages.
"""

import numpy as np
import pytest
from Basilisk.architecture import messaging
from Basilisk.utilities import SimulationBaseClass, macros

from gnc_cdh.basilisk import AlgorithmModule

ONE_SECOND_NS = 1_000_000_000

STEPPED = np.array([1.0, 2.0, 3.0])
"""The arrays the stub steps its outputs to at t = 1 s; at time t it steps them to `t * STEPPED`."""


class StubAlgorithm:
    """A stub algorithm that records what reaches it.

    It reads `AngVelPlatform` from an IMU message and `sigma_BN` from a navigation message, holds
    `t`, `r_BN_N` and `v_BN_N`, and steps its outputs to `t * STEPPED` and `-t * STEPPED`.
    """

    def __init__(self, t0: float = 0.0, r0: tuple[float, float, float] = (0.5, 0.5, 0.5)) -> None:
        """Starts the stub's state.

        Args:
            t0: s, the time the state applies at.
            r0: (3,) m, the initial `r_BN_N`, in N; `v_BN_N` starts at -`r0`, in m/s.
        """
        self._steps: list[dict] = []
        self.t = t0
        self.r_BN_N = np.asarray(r0, dtype=float)
        self.v_BN_N = -np.asarray(r0, dtype=float)

    def step(self, t: float, AngVelPlatform: np.ndarray, sigma_BN: np.ndarray) -> dict:
        """Records the step's inputs and steps the outputs.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.
            sigma_BN: (3,) MRP, read from the navigation message.

        Returns:
            `r_BN_N` ((3,) m, in N) and `v_BN_N` ((3,) m/s, in N) as named arrays.
        """
        self._steps.append({"t": t, "AngVelPlatform": AngVelPlatform, "sigma_BN": sigma_BN})
        self.t, self.r_BN_N, self.v_BN_N = t, t * STEPPED, -t * STEPPED
        return {"r_BN_N": self.r_BN_N, "v_BN_N": self.v_BN_N}


class UnreadKeyword(StubAlgorithm):
    """A stub whose `step` asks for a field no input's message carries."""

    def step(self, t: float, AngVelPlatfrom: np.ndarray) -> dict:
        """Asks for a misspelled field, which construction refuses before any step.

        Args:
            t: s, the step's time.
            AngVelPlatfrom: (3,) rad/s, a field no input's message carries.

        Returns:
            No outputs.
        """
        return {}


class UnknownOutput(StubAlgorithm):
    """A stub holding an output, `value`, that is not an estimate `gnc_cdh.UNITS` names."""

    def __init__(self) -> None:
        """Starts as `StubAlgorithm` does, plus `value` ((3,))."""
        super().__init__()
        self.value = np.zeros(3)


class InPlace(StubAlgorithm):
    """A stub that steps its outputs by writing into the arrays it holds."""

    def step(self, t: float, AngVelPlatform: np.ndarray, sigma_BN: np.ndarray) -> dict:
        """Steps the outputs in place.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.
            sigma_BN: (3,) MRP, read from the navigation message.

        Returns:
            `r_BN_N` and `v_BN_N`, the arrays the stub holds.
        """
        self.t = t
        self.r_BN_N[:] = t * STEPPED
        self.v_BN_N[:] = -t * STEPPED
        return {"r_BN_N": self.r_BN_N, "v_BN_N": self.v_BN_N}


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


def _module(algorithm: StubAlgorithm | None = None) -> AlgorithmModule:
    """A stub algorithm hosted on `_readers()`.

    Args:
        algorithm: the algorithm to host; a fresh `StubAlgorithm` when `None`.

    Returns:
        The `AlgorithmModule`.
    """
    return AlgorithmModule(StubAlgorithm() if algorithm is None else algorithm, _readers())


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


def test_each_step_keyword_is_read_from_the_message_carrying_that_field():
    """A step receives `t` in s and each keyword from the input whose message has that field."""
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    step = module.algorithm._steps[-1]
    assert step["t"] == 1.0
    np.testing.assert_array_equal(step["AngVelPlatform"], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(step["sigma_BN"], [0.4, 0.5, 0.6])


def test_reset_and_each_step_log_the_estimate_by_the_tick_s_time():
    """The estimate is the outputs as held at the reset, then as each step returns them."""
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    datasets = module.estimate_datasets(np.array([0.0, 1.0]))
    assert sorted(datasets) == ["est/r_BN_N", "est/v_BN_N"]
    np.testing.assert_array_equal(datasets["est/r_BN_N"][0], [[0.5, 0.5, 0.5], STEPPED])
    np.testing.assert_array_equal(datasets["est/v_BN_N"][0], [[-0.5, -0.5, -0.5], -STEPPED])
    assert (datasets["est/r_BN_N"][1], datasets["est/v_BN_N"][1]) == ("m", "m/s")


def test_the_log_keeps_each_tick_s_values_when_the_algorithm_changes_its_arrays_in_place():
    """An algorithm that steps by mutating its arrays still leaves each tick's values in the log."""
    module = _module(InPlace())
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    rows = module.estimate_datasets(np.array([0.0, 1.0]))["est/r_BN_N"][0]
    np.testing.assert_array_equal(rows, [[0.5, 0.5, 0.5], STEPPED])


def test_the_estimate_names_a_record_time_no_tick_logged():
    """A record time between ticks is refused by its time."""
    module = _module()
    _messages = _subscribed(module)
    module.Reset(0)

    with pytest.raises(KeyError, match="no estimate was logged at t = 0.5 s"):
        module.estimate_datasets(np.array([0.5]))


def test_the_call_at_the_reset_time_does_not_step():
    """The `UpdateState` Basilisk makes at the reset time leaves the state as built."""
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(0)
    assert module.algorithm._steps == []

    module.UpdateState(ONE_SECOND_NS)
    assert len(module.algorithm._steps) == 1


def test_construction_names_a_keyword_no_input_carries():
    """A `step` keyword that no input's message has as a field is refused by name."""
    with pytest.raises(ValueError, match=r"'AngVelPlatfrom' is carried by 0 inputs"):
        _module(UnreadKeyword())


def test_construction_names_a_keyword_two_inputs_carry():
    """A `step` keyword that two inputs' messages both carry is refused by name."""
    readers = {
        "imu_a": messaging.IMUSensorMsgReader(),
        "imu_b": messaging.IMUSensorMsgReader(),
        "nav": messaging.NavAttMsgReader(),
    }
    with pytest.raises(ValueError, match=r"'AngVelPlatform' is carried by 2 inputs"):
        AlgorithmModule(StubAlgorithm(), readers)


def test_construction_names_an_output_that_is_not_an_estimate():
    """An output name that `gnc_cdh.UNITS` does not name is refused by name."""
    with pytest.raises(ValueError, match=r"outputs \['value'\] are not estimates"):
        _module(UnknownOutput())


def test_the_input_table_is_read_only():
    """The input readers cannot be replaced."""
    module = _module()

    with pytest.raises(TypeError):
        module.inputs["extra"] = messaging.NavAttMsgReader()


def test_reset_names_an_unsubscribed_input():
    """`Reset` names the input reader that is not subscribed."""
    module = _module()
    imu = _imu_message()
    module.inputs["imu"].subscribeTo(imu)

    with pytest.raises(RuntimeError, match=r"\['nav'\] are not subscribed"):
        module.Reset(0)


def test_a_step_names_an_input_never_written():
    """A step names the subscribed input that has never been written."""
    module = _module()
    imu, nav = _imu_message(), messaging.NavAttMsg()  # nav subscribed, never written
    module.inputs["imu"].subscribeTo(imu)
    module.inputs["nav"].subscribeTo(nav)
    module.Reset(0)

    with pytest.raises(RuntimeError, match=r"\['nav'\] have not been written"):
        module.UpdateState(ONE_SECOND_NS)


def test_a_task_at_the_module_period_logs_the_estimate_at_whole_seconds():
    """Run 3.5 s in a task every `period_s`, the estimate is logged at 0, 1, 2 and 3 s only."""
    module = _module()
    _messages = _subscribed(module)
    sim = SimulationBaseClass.SimBaseClass()
    sim.CreateNewProcess("process").addTask(
        sim.CreateNewTask("task", macros.sec2nano(module.period_s))
    )
    sim.AddModelToTask("task", module)

    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(3.5))
    sim.ExecuteSimulation()

    rows = module.estimate_datasets(np.array([0.0, 1.0, 2.0, 3.0]))["est/r_BN_N"][0]
    np.testing.assert_array_equal(rows[1:], [STEPPED, 2 * STEPPED, 3 * STEPPED])
    with pytest.raises(KeyError):
        module.estimate_datasets(np.array([3.5]))
    assert module.algorithm.t == 3.0


def test_the_build_names_the_host():
    """`build` is exactly the host's name."""
    assert _module().build == {"host": "gnc_cdh.basilisk.AlgorithmModule"}
