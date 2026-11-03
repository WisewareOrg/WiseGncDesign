"""`AlgorithmModule` driven directly, with a stub algorithm and standalone Basilisk messages."""

import dataclasses
from dataclasses import dataclass, field

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.basilisk import AlgorithmModule, InputMap, OutputMap

ONE_SECOND_NS = 1_000_000_000


@dataclass(frozen=True)
class StubSample:
    """A sample with two vector fields, `a` and `b`."""

    t: float
    a: np.ndarray
    b: np.ndarray


@dataclass(frozen=True)
class StubState:
    """A state carrying one vector, `value`."""

    t: float
    value: np.ndarray = field(default_factory=lambda: np.zeros(3))


class StubAlgorithm:
    """Records every sample and steps to `STEPPED_VALUE`, so a test sees what reached it."""

    STEPPED_VALUE = np.array([1.0, 2.0, 3.0])

    def __init__(self, t0: float, init: dict) -> None:
        self.samples: list[StubSample] = []
        self._state = StubState(t=t0, value=np.asarray(init.get("value0", np.zeros(3))))

    @property
    def state(self) -> StubState:
        return self._state

    def step(self, sample: StubSample) -> StubState:
        self.samples.append(sample)
        self._state = StubState(t=sample.t, value=self.STEPPED_VALUE)
        return self._state


def _imu_message(angvel=(0.0, 0.0, 0.0), accel=(0.0, 0.0, 0.0)) -> messaging.IMUSensorMsg:
    msg = messaging.IMUSensorMsg()
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = list(angvel)
    payload.AccelPlatform = list(accel)
    msg.write(payload, 0, 0)
    return msg


def _nav_message(sigma=(0.0, 0.0, 0.0)) -> messaging.NavAttMsg:
    msg = messaging.NavAttMsg()
    payload = messaging.NavAttMsgPayload()
    payload.sigma_BN = list(sigma)
    msg.write(payload, 0, 0)
    return msg


IMU_TO_A = InputMap("imu", "AngVelPlatform", "a")
NAV_TO_B = InputMap("nav", "sigma_BN", "b")


def _module(**overrides) -> AlgorithmModule:
    """Two inputs (`imu`, `nav`) into `a` and `b`; `value` out to two messages."""
    arguments = {
        "inputs": {"imu": messaging.IMUSensorMsgReader(), "nav": messaging.NavAttMsgReader()},
        "outputs": {"att": messaging.NavAttMsg(), "trans": messaging.NavTransMsg()},
        "input_maps": [InputMap("imu", "AngVelPlatform", "a"), InputMap("nav", "sigma_BN", "b")],
        "output_maps": [
            OutputMap("value", "att", "sigma_BN"),
            OutputMap("value", "trans", "r_BN_N"),
        ],
        "sample_type": StubSample,
        "make_algorithm": StubAlgorithm,
        "init_from": lambda: {"value0": np.array([0.5, 0.5, 0.5])},
    }
    return AlgorithmModule(**{**arguments, **overrides})


def _subscribed(module: AlgorithmModule, angvel=(1.0, 2.0, 3.0), sigma=(0.4, 0.5, 0.6)):
    imu, nav = _imu_message(angvel), _nav_message(sigma)
    module.inputs["imu"].subscribeTo(imu)
    module.inputs["nav"].subscribeTo(nav)
    return imu, nav


def test_each_payload_field_lands_in_its_sample_field():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    sample = module.algorithm.samples[-1]
    assert sample.t == 1.0
    np.testing.assert_array_equal(sample.a, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(sample.b, [0.4, 0.5, 0.6])


def test_a_transform_is_applied_before_the_value_reaches_the_sample():
    rotate_z_90 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    module = _module(
        input_maps=[
            InputMap("imu", "AngVelPlatform", "a", transform=lambda v: rotate_z_90 @ v),
            NAV_TO_B,
        ]
    )
    _messages = _subscribed(module, angvel=(1.0, 0.0, 0.0))

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    np.testing.assert_allclose(module.algorithm.samples[-1].a, [0.0, 1.0, 0.0], atol=1e-15)


def test_reset_writes_the_initial_state_to_every_output():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)

    np.testing.assert_array_equal(module.output_messages["att"].read().sigma_BN, [0.5, 0.5, 0.5])
    np.testing.assert_array_equal(module.output_messages["trans"].read().r_BN_N, [0.5, 0.5, 0.5])


def test_a_step_writes_the_new_state_to_every_output():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    stepped = StubAlgorithm.STEPPED_VALUE
    np.testing.assert_array_equal(module.output_messages["att"].read().sigma_BN, stepped)
    np.testing.assert_array_equal(module.output_messages["trans"].read().r_BN_N, stepped)


def test_the_call_at_the_reset_time_does_not_step():
    module = _module()
    _messages = _subscribed(module)

    module.Reset(0)
    module.UpdateState(0)
    assert module.algorithm.samples == []

    module.UpdateState(ONE_SECOND_NS)
    assert len(module.algorithm.samples) == 1


def test_called_every_step_the_output_changes_only_at_whole_seconds():
    module = _module()
    _messages = _subscribed(module)
    written = messaging.NavAttMsgReader()
    written.subscribeTo(module.output_messages["att"])
    step_ns = 20_000_000

    module.Reset(0)
    write_times = {written.timeWritten()}
    for k in range(1, 3 * ONE_SECOND_NS // step_ns + 1):
        module.UpdateState(k * step_ns)
        write_times.add(written.timeWritten())

    assert sorted(write_times) == [0, ONE_SECOND_NS, 2 * ONE_SECOND_NS, 3 * ONE_SECOND_NS]
    assert [sample.t for sample in module.algorithm.samples] == [1.0, 2.0, 3.0]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"input_maps": [InputMap("gps", "AngVelPlatform", "a")]}, "unknown input 'gps'"),
        (
            {
                "input_maps": [
                    InputMap("imu", "AngVelPltaform", "a"),
                    InputMap("nav", "sigma_BN", "b"),
                ]
            },
            "unknown payload field 'AngVelPltaform'",
        ),
        (
            {
                "input_maps": [
                    InputMap("imu", "AngVelPlatform", "c"),
                    InputMap("nav", "sigma_BN", "b"),
                ]
            },
            "unknown field 'c'",
        ),
        (
            {
                "input_maps": [
                    InputMap("imu", "AngVelPlatform", "a"),
                    InputMap("nav", "sigma_BN", "a"),
                ]
            },
            r"feed \['a'\] more than once",
        ),
        ({"input_maps": [InputMap("imu", "AngVelPlatform", "a")]}, r"leave \['b'\]"),
        ({"output_maps": [OutputMap("value", "pos", "r_BN_N")]}, "unknown output 'pos'"),
        (
            {"output_maps": [OutputMap("value", "att", "sigma_NB")]},
            "unknown payload field 'sigma_NB'",
        ),
        ({"sample_type": dict}, "not a dataclass"),
    ],
)
def test_construction_names_the_first_invalid_map(overrides, message):
    with pytest.raises(ValueError, match=message):
        _module(**overrides)


def test_an_output_map_carries_no_transform():
    with pytest.raises(TypeError):
        OutputMap("value", "att", "sigma_BN", transform=lambda v: v)


def test_maps_and_message_tables_are_read_only():
    module = _module()

    assert isinstance(module.input_maps, tuple)
    assert isinstance(module.output_maps, tuple)
    with pytest.raises(TypeError):
        module.output_messages["extra"] = messaging.NavAttMsg()
    with pytest.raises(AttributeError):
        module.input_maps = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        module.input_maps[0].sample_field = "b"


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


def test_reset_names_an_output_map_whose_state_field_is_missing():
    module = _module(output_maps=[OutputMap("velocity", "att", "sigma_BN")])
    _messages = _subscribed(module)

    with pytest.raises(ValueError, match="'velocity'"):
        module.Reset(0)
