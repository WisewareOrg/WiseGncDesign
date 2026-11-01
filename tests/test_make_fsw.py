"""`make_fsw` end to end against standalone Basilisk messages, written directly."""

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.basilisk import make_fsw


def _write_imu(angvel, accel) -> messaging.IMUSensorMsg:
    msg = messaging.IMUSensorMsg()
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = list(angvel)
    payload.AccelPlatform = list(accel)
    msg.write(payload, 0, 0)
    return msg


def test_make_fsw_builds_imu_dead_reckoning_and_steps_it():
    imu_reader = messaging.IMUSensorMsgReader()
    imu_reader.subscribeTo(_write_imu([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]))
    r0_N = np.array([7.0e6, 0.0, 0.0])

    module = make_fsw(
        "imu_dead_reckoning",
        inputs={"imu": imu_reader},
        initial_state=lambda: {"sigma0_BN": np.zeros(3), "r0_N": r0_N, "v0_N": np.zeros(3)},
        mu=0.0,
    )

    module.Reset(0)
    module.UpdateState(1_000_000_000)  # 1 s later

    assert module.algorithm.state.t == 1.0
    out_att = module.outputs["nav_att"][1].read()
    out_trans = module.outputs["nav_trans"][1].read()
    np.testing.assert_allclose(out_att.sigma_BN, module.algorithm.state.sigma_BN)
    np.testing.assert_allclose(out_trans.r_BN_N, module.algorithm.state.r_N)
    np.testing.assert_allclose(out_trans.v_BN_N, module.algorithm.state.v_N)
    # mu = 0, zero rate: accel_B = [1, 0, 0] at identity attitude integrates to v_N = [1, 0, 0].
    np.testing.assert_allclose(module.algorithm.state.v_N, [1.0, 0.0, 0.0], atol=1e-9)


def test_make_fsw_applies_a_non_identity_platform_to_body_mounting():
    # 90 deg rotation about +Z: platform-frame x becomes body-frame +y under this matrix's
    # transpose (the same convention tests/test_algorithm_module.py pins for AlgorithmModule
    # itself; this test pins that make_fsw resolves the neutral "platform_to_body" frame to it).
    dcm_PB = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    imu_reader = messaging.IMUSensorMsgReader()
    imu_reader.subscribeTo(_write_imu([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]))
    r0_N = np.array([7.0e6, 0.0, 0.0])

    module = make_fsw(
        "imu_dead_reckoning",
        inputs={"imu": imu_reader},
        initial_state=lambda: {"sigma0_BN": np.zeros(3), "r0_N": r0_N, "v0_N": np.zeros(3)},
        mountings={"imu": dcm_PB},
        mu=0.0,
    )

    module.Reset(0)
    module.UpdateState(1_000_000_000)

    expected_v = dcm_PB.T @ np.array([1.0, 0.0, 0.0])
    np.testing.assert_allclose(module.algorithm.state.v_N, expected_v, atol=1e-9)
    assert not np.allclose(expected_v, [1.0, 0.0, 0.0])  # the mounting actually did something


def test_make_fsw_raises_when_initial_state_is_missing_a_declared_init_key():
    imu_reader = messaging.IMUSensorMsgReader()
    imu_reader.subscribeTo(_write_imu([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]))

    module = make_fsw(
        "imu_dead_reckoning",
        inputs={"imu": imu_reader},
        initial_state=lambda: {"sigma0_BN": np.zeros(3), "v0_N": np.zeros(3)},  # r0_N missing
        mu=0.0,
    )

    with pytest.raises(ValueError, match="r0_N"):
        module.Reset(0)


def test_make_fsw_raises_when_mu_is_not_supplied_as_a_param():
    # mu arrives via **params, not initial_state(), so it needs its own regression check: the
    # validation has to cover init_keys against the *merged* dict, not just initial_state()'s.
    imu_reader = messaging.IMUSensorMsgReader()
    imu_reader.subscribeTo(_write_imu([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]))

    module = make_fsw(
        "imu_dead_reckoning",
        inputs={"imu": imu_reader},
        initial_state=lambda: {
            "sigma0_BN": np.zeros(3),
            "r0_N": np.array([7.0e6, 0.0, 0.0]),
            "v0_N": np.zeros(3),
        },
        # no mu= kwarg
    )

    # match the exact missing-key list, not the bare substring "mu": "imu_dead_reckoning" also
    # contains "mu", so match="mu" would pass even if the wrong key were reported as missing.
    with pytest.raises(ValueError, match=r"\['mu'\]"):
        module.Reset(0)
