"""`AlgorithmModule` driven directly, with a stub algorithm, a stub binding and standalone
Basilisk messages."""

import dataclasses

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.basilisk import AlgorithmModule, Binding

ONE_SECOND_NS = 1_000_000_000


class StubAlgorithm:
    """Holds `t`, `value` and `other`, records every step's inputs, and steps to `STEPPED`, so a
    test sees what reached it."""

    STEPPED = np.array([1.0, 2.0, 3.0])

    def __init__(self, t0: float, value0: np.ndarray) -> None:
        self.steps: list[dict] = []
        self.t = t0
        self.value = np.asarray(value0)
        self.other = -np.asarray(value0)

    def step(self, t: float, a: np.ndarray, b: np.ndarray) -> dict[str, np.ndarray]:
        self.steps.append({"t": t, "a": a, "b": b})
        self.t, self.value, self.other = t, self.STEPPED, -self.STEPPED
        return {"value": self.value, "other": self.other}


BINDING = Binding(
    algorithm=StubAlgorithm,
    inputs={"a": ("imu", "AngVelPlatform"), "b": ("nav", "sigma_BN")},
    outputs={"value": ("att", "sigma_BN"), "other": ("trans", "r_BN_N")},
    messages={"att": messaging.NavAttMsg, "trans": messaging.NavTransMsg},
)


def _imu_message(angvel=(0.0, 0.0, 0.0)) -> messaging.IMUSensorMsg:
    msg = messaging.IMUSensorMsg()
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = list(angvel)
    msg.write(payload, 0, 0)
    return msg


def _nav_message(sigma=(0.0, 0.0, 0.0)) -> messaging.NavAttMsg:
    msg = messaging.NavAttMsg()
    payload = messaging.NavAttMsgPayload()
    payload.sigma_BN = list(sigma)
    msg.write(payload, 0, 0)
    return msg


def _module(**overrides) -> AlgorithmModule:
    """`BINDING` with `overrides` replacing its fields, on an `imu` and a `nav` reader."""
    return AlgorithmModule(
        dataclasses.replace(BINDING, **overrides),
        inputs={"imu": messaging.IMUSensorMsgReader(), "nav": messaging.NavAttMsgReader()},
        init_from=lambda: {"value0": np.array([0.5, 0.5, 0.5])},
    )


def _subscribed(module: AlgorithmModule, angvel=(1.0, 2.0, 3.0), sigma=(0.4, 0.5, 0.6)):
    imu, nav = _imu_message(angvel), _nav_message(sigma)
    module.inputs["imu"].subscribeTo(imu)
    module.inputs["nav"].subscribeTo(nav)
    return imu, nav


def test_each_message_field_reaches_its_step_keyword():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    step = module.algorithm.steps[-1]
    assert step["t"] == 1.0
    np.testing.assert_array_equal(step["a"], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(step["b"], [0.4, 0.5, 0.6])


def test_reset_writes_the_initial_state_to_every_output():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)

    np.testing.assert_array_equal(module.output_messages["att"].read().sigma_BN, [0.5, 0.5, 0.5])
    np.testing.assert_array_equal(module.output_messages["trans"].read().r_BN_N, [-0.5, -0.5, -0.5])


def test_a_step_writes_the_new_state_to_every_output():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    np.testing.assert_array_equal(
        module.output_messages["att"].read().sigma_BN, StubAlgorithm.STEPPED
    )
    np.testing.assert_array_equal(
        module.output_messages["trans"].read().r_BN_N, -StubAlgorithm.STEPPED
    )


def test_the_call_at_the_reset_time_does_not_step():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(0)
    assert module.algorithm.steps == []

    module.UpdateState(ONE_SECOND_NS)
    assert len(module.algorithm.steps) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"inputs": {"a": ("imu", "AngVelPlatform")}}, r"inputs name \['a'\]; StubAlgorithm.step"),
        (
            {"inputs": {**BINDING.inputs, "c": ("nav", "sigma_BN")}},
            r"inputs name \['a', 'b', 'c'\]",
        ),
        ({"inputs": {"a": ("gps", "AngVelPlatform"), "b": BINDING.inputs["b"]}}, "role 'gps'"),
        (
            {"inputs": {"a": ("imu", "AngVelPltaform"), "b": BINDING.inputs["b"]}},
            "no field 'AngVelPltaform'",
        ),
        ({"outputs": {"value": ("pos", "r_BN_N")}}, "message 'pos', absent from messages"),
        ({"outputs": {"value": ("att", "sigma_NB")}}, "'att' has no field 'sigma_NB'"),
    ],
)
def test_construction_names_what_the_binding_gets_wrong(overrides, message):
    with pytest.raises(ValueError, match=message):
        _module(**overrides)


def test_the_message_tables_are_read_only():
    module = _module()

    with pytest.raises(TypeError):
        module.output_messages["extra"] = messaging.NavAttMsg()
    with pytest.raises(TypeError):
        module.inputs["extra"] = messaging.NavAttMsgReader()


def test_the_algorithm_is_unavailable_before_reset():
    module = _module()

    with pytest.raises(RuntimeError, match="not been Reset"):
        _ = module.algorithm
    with pytest.raises(RuntimeError, match="not been Reset"):
        module.UpdateState(ONE_SECOND_NS)


def test_reset_names_an_unsubscribed_input():
    module = _module()
    imu = _imu_message()
    module.inputs["imu"].subscribeTo(imu)

    with pytest.raises(RuntimeError, match=r"\['nav'\] are not subscribed"):
        module.Reset(0)


def test_a_step_names_an_input_never_written():
    module = _module()
    imu, nav = _imu_message(), messaging.NavAttMsg()  # nav subscribed, never written
    module.inputs["imu"].subscribeTo(imu)
    module.inputs["nav"].subscribeTo(nav)
    module.Reset(0)

    with pytest.raises(RuntimeError, match=r"\['nav'\] have not been written"):
        module.UpdateState(ONE_SECOND_NS)


def test_reset_names_an_output_the_algorithm_holds_no_attribute_for():
    module = _module(outputs={"velocity": ("att", "sigma_BN")})
    _messages = _subscribed(module)

    with pytest.raises(ValueError, match="'velocity'"):
        module.Reset(0)
