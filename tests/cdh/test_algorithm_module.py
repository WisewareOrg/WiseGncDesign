"""`AlgorithmModule` driven directly.

It hosts stub algorithms, wired by their names, on standalone Basilisk messages.
"""

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.basilisk import AlgorithmModule

ONE_SECOND_NS = 1_000_000_000

STEPPED = np.array([1.0, 2.0, 3.0])
"""The arrays the stub steps its outputs to."""


class StubAlgorithm:
    """A stub algorithm that records what reaches it.

    It reads `AngVelPlatform` from an IMU message and `sigma_BN` from a navigation message, holds
    `t`, `r_BN_N` and `v_BN_N`, and steps its outputs to `STEPPED` and `-STEPPED`.
    """

    def __init__(self, t0: float = 0.0, r0: np.ndarray = (0.5, 0.5, 0.5)) -> None:
        """Starts at `t0` (s) with `r_BN_N` = `r0` ((3,), m) and `v_BN_N` = -`r0` (m/s)."""
        self._steps: list[dict] = []
        self.t = t0
        self.r_BN_N = np.asarray(r0, dtype=float)
        self.v_BN_N = -np.asarray(r0, dtype=float)

    def step(self, t: float, AngVelPlatform: np.ndarray, sigma_BN: np.ndarray) -> dict:
        """Records the step's inputs and steps the outputs.

        Takes `t` (s), `AngVelPlatform` (rad/s, (3,)) and `sigma_BN` (MRP, (3,)); returns `r_BN_N`
        and `v_BN_N` as named arrays.
        """
        self._steps.append({"t": t, "AngVelPlatform": AngVelPlatform, "sigma_BN": sigma_BN})
        self.t, self.r_BN_N, self.v_BN_N = t, STEPPED, -STEPPED
        return {"r_BN_N": self.r_BN_N, "v_BN_N": self.v_BN_N}


class UnreadKeyword(StubAlgorithm):
    """A stub whose `step` asks for a field no input's message carries."""

    def step(self, t: float, AngVelPlatfrom: np.ndarray) -> dict:
        """Takes `t` (s) and a misspelled `AngVelPlatfrom`; returns nothing it is given."""
        return {}


class UnknownOutput(StubAlgorithm):
    """A stub holding an output, `value`, that no standard message carries."""

    def __init__(self) -> None:
        """Starts as `StubAlgorithm` does, plus `value` ((3,))."""
        super().__init__()
        self.value = np.zeros(3)


def _imu_message(angvel=(0.0, 0.0, 0.0)) -> messaging.IMUSensorMsg:
    """A written `IMUSensorMsg` whose `AngVelPlatform` is `angvel` (rad/s, (3,))."""
    msg = messaging.IMUSensorMsg()
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = list(angvel)
    msg.write(payload, 0, 0)
    return msg


def _nav_message(sigma=(0.0, 0.0, 0.0)) -> messaging.NavAttMsg:
    """A written `NavAttMsg` whose `sigma_BN` is `sigma` (MRP, (3,))."""
    msg = messaging.NavAttMsg()
    payload = messaging.NavAttMsgPayload()
    payload.sigma_BN = list(sigma)
    msg.write(payload, 0, 0)
    return msg


def _readers() -> dict:
    """An unsubscribed `imu` and `nav` reader, by role."""
    return {"imu": messaging.IMUSensorMsgReader(), "nav": messaging.NavAttMsgReader()}


def _module(algorithm=None) -> AlgorithmModule:
    """`algorithm` (default a fresh `StubAlgorithm`) hosted on `_readers()`."""
    return AlgorithmModule(StubAlgorithm() if algorithm is None else algorithm, _readers())


def _subscribed(module: AlgorithmModule, angvel=(1.0, 2.0, 3.0), sigma=(0.4, 0.5, 0.6)):
    """Subscribes `module`'s `imu` and `nav` readers to written messages.

    The messages carry `angvel` (rad/s, (3,)) and `sigma` (MRP, (3,)), and are returned so they
    outlive the call.
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


def test_each_output_goes_to_the_standard_message_carrying_its_name():
    """`r_BN_N` and `v_BN_N` go to `nav_trans`, the only message created."""
    module = _module()

    assert sorted(module.output_messages) == ["nav_trans"]
    assert set(module.outputs) == {"r_BN_N", "v_BN_N"}


def test_reset_writes_the_initial_state_to_every_output():
    """`Reset` writes the algorithm's `r_BN_N` and `v_BN_N` as it holds them."""
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)

    payload = module.output_messages["nav_trans"].read()
    np.testing.assert_array_equal(payload.r_BN_N, [0.5, 0.5, 0.5])
    np.testing.assert_array_equal(payload.v_BN_N, [-0.5, -0.5, -0.5])


def test_a_step_writes_the_returned_arrays_to_every_output():
    """A step writes the arrays `step` returns to their message fields."""
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    payload = module.output_messages["nav_trans"].read()
    np.testing.assert_array_equal(payload.r_BN_N, STEPPED)
    np.testing.assert_array_equal(payload.v_BN_N, -STEPPED)


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


def test_construction_names_an_output_no_standard_message_carries():
    """An output name that no standard message has as a field is refused by name."""
    with pytest.raises(ValueError, match=r"carries the outputs \['value'\]"):
        _module(UnknownOutput())


def test_the_message_tables_are_read_only():
    """Neither the input readers nor the output messages can be replaced."""
    module = _module()

    with pytest.raises(TypeError):
        module.output_messages["extra"] = messaging.NavAttMsg()
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
