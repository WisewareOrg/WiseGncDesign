"""`make_fsw` end to end against standalone Basilisk messages: no plant, no running task."""

import numpy as np
from Basilisk.architecture import messaging

from hosts.basilisk import make_fsw


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
    out_att = module.outputs["navAtt"][1].read()
    out_trans = module.outputs["navTrans"][1].read()
    np.testing.assert_allclose(out_att.sigma_BN, module.algorithm.state.sigma_BN)
    np.testing.assert_allclose(out_trans.r_BN_N, module.algorithm.state.r_N)
    np.testing.assert_allclose(out_trans.v_BN_N, module.algorithm.state.v_N)
    # mu = 0, zero rate: accel_B = [1, 0, 0] at identity attitude integrates to v_N = [1, 0, 0].
    np.testing.assert_allclose(module.algorithm.state.v_N, [1.0, 0.0, 0.0], atol=1e-9)
