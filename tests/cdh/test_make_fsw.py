"""`make_fsw` building the dead reckoner against standalone Basilisk messages."""

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.basilisk import make_fsw

ONE_SECOND_NS = 1_000_000_000
R0_N = np.array([7.0e6, 0.0, 0.0])
IDENTITY = {"imu": np.eye(3)}


def _initial_state() -> dict[str, np.ndarray]:
    return {"sigma0_BN": np.zeros(3), "r0_N": R0_N, "v0_N": np.zeros(3)}


@pytest.fixture
def imu_reader():
    """An IMU reader subscribed to a message reading zero rate and 1 m/s^2 along platform x."""
    msg = messaging.IMUSensorMsg()
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = [0.0, 0.0, 0.0]
    payload.AccelPlatform = [1.0, 0.0, 0.0]
    msg.write(payload, 0, 0)
    reader = messaging.IMUSensorMsgReader()
    reader.subscribeTo(msg)
    reader.message = msg  # keeps the message alive as long as the reader
    return reader


def _fsw(imu_reader, **overrides):
    arguments = {
        "inputs": {"imu": imu_reader},
        "initial_state": _initial_state,
        "mountings": IDENTITY,
        "mu": 0.0,
    }
    return make_fsw("imu_dead_reckoning", **{**arguments, **overrides})


def test_builds_and_steps_the_dead_reckoner_and_publishes_its_state(imu_reader):
    module = _fsw(imu_reader)

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    state = module.algorithm.state
    assert state.t == 1.0
    # mu = 0, zero rate, identity attitude: 1 m/s^2 along x for 1 s.
    np.testing.assert_allclose(state.v_N, [1.0, 0.0, 0.0], atol=1e-12)
    assert set(module.output_messages) == {"nav_att", "nav_trans"}
    np.testing.assert_array_equal(module.output_messages["nav_att"].read().sigma_BN, state.sigma_BN)
    np.testing.assert_array_equal(module.output_messages["nav_trans"].read().r_BN_N, state.r_N)
    np.testing.assert_array_equal(module.output_messages["nav_trans"].read().v_BN_N, state.v_N)


def test_a_mounting_rotates_platform_readings_into_the_body_frame(imu_reader):
    # [PB] for P rotated +90 deg about z from B: platform x is body -y.
    dcm_PB = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    module = _fsw(imu_reader, mountings={"imu": dcm_PB})

    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS)

    np.testing.assert_allclose(module.algorithm.state.v_N, [0.0, 1.0, 0.0], atol=1e-12)


def test_initial_state_keys_naming_no_parameter_are_left_out(imu_reader):
    module = _fsw(imu_reader, initial_state=lambda: {**_initial_state(), "omega0_BN_B": [1, 2, 3]})

    module.Reset(0)

    np.testing.assert_array_equal(module.algorithm.state.r_N, R0_N)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mountings": None}, r"roles \['imu'\] need a mounting"),
        ({"mountings": {"imu": np.eye(3), "gps": np.eye(3)}}, r"mountings for \['gps'\]"),
        ({"mountings": {"imu": np.eye(2)}}, "not an orthonormal"),
        ({"mountings": {"imu": 2.0 * np.eye(3)}}, "not an orthonormal"),
        ({"inputs": {}}, "inputs has no role 'imu'"),
        ({"inputs": {"imu": messaging.NavAttMsgReader()}}, "expected IMUSensorMsgReader"),
        ({"muu": 0.0}, r"params \['muu'\]"),
    ],
)
def test_construction_names_the_invalid_argument(imu_reader, overrides, message):
    with pytest.raises(ValueError, match=message):
        _fsw(imu_reader, **overrides)


def test_an_unknown_algorithm_lists_the_known_ones(imu_reader):
    with pytest.raises(ValueError, match=r"no algorithm 'nope'; known: \['imu_dead_reckoning'\]"):
        make_fsw("nope", inputs={"imu": imu_reader}, initial_state=_initial_state)


def test_reset_names_a_missing_initial_state_key(imu_reader):
    module = _fsw(imu_reader, initial_state=lambda: {"sigma0_BN": np.zeros(3), "v0_N": np.zeros(3)})

    with pytest.raises(ValueError, match=r"\['r0_N'\]"):
        module.Reset(0)


def test_reset_names_a_missing_mu(imu_reader):
    module = make_fsw(
        "imu_dead_reckoning",
        inputs={"imu": imu_reader},
        initial_state=_initial_state,
        mountings=IDENTITY,
    )

    with pytest.raises(ValueError, match=r"\['mu'\]"):
        module.Reset(0)


def test_reset_names_a_key_supplied_twice(imu_reader):
    module = _fsw(imu_reader, r0_N=R0_N)

    with pytest.raises(ValueError, match=r"both supply \['r0_N'\]"):
        module.Reset(0)
