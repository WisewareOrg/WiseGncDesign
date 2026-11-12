"""The F´ host's refusals and its run-file datasets, against messages written by hand.

Needs the deployment `just fsw` builds.
"""

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.fprime import FprimeModule

ONE_SECOND_NS = 1_000_000_000

INITIAL = {
    "sigma0_BN": np.array([0.1, 0.2, -0.3]),
    "r0_N": np.array([6871.0e3, 0.0, 0.0]),
    "v0_N": np.array([0.0, 5.4e3, 5.4e3]),
}
"""A dead reckoner's state at t = 0, in the shape of a scenario's `initial_state()`."""


def _module() -> FprimeModule:
    """A host on an unsubscribed IMU reader, mounted at identity.

    Returns:
        The `FprimeModule`.
    """
    return FprimeModule(
        messaging.IMUSensorMsgReader(), mu=3.986004360e14, dcm_PB=np.eye(3), initial=INITIAL
    )


def test_reset_refuses_an_unsubscribed_imu():
    """`Reset` names the IMU reader that no message feeds."""
    with pytest.raises(RuntimeError, match="IMU reader is not subscribed"):
        _module().Reset(0)


def test_a_tick_refuses_an_imu_never_written():
    """A tick after the reset names the IMU message that has never been written."""
    module = _module()
    imu = messaging.IMUSensorMsg()
    module._imu.subscribeTo(imu)
    module.Reset(0)

    with pytest.raises(RuntimeError, match=r"IMU has not been written at t = 1.0 s"):
        module.UpdateState(ONE_SECOND_NS)


def test_the_estimate_datasets_are_the_logged_ticks_and_refuse_a_time_never_logged():
    """`estimate_datasets` gives the state at each logged tick, and names a time no tick logged."""
    module = _module()
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)
    module.UpdateState(ONE_SECOND_NS // 10)

    datasets = module.estimate_datasets(np.array([0.0, 0.1]))

    assert sorted(datasets) == ["est/r_BN_N", "est/sigma_BN", "est/v_BN_N"]
    np.testing.assert_allclose(datasets["est/sigma_BN"][0][0], INITIAL["sigma0_BN"], atol=1e-15)
    np.testing.assert_array_equal(datasets["est/r_BN_N"][0][0], INITIAL["r0_N"])
    assert datasets["est/r_BN_N"][1] == "m"
    assert not np.array_equal(datasets["est/r_BN_N"][0][1], INITIAL["r0_N"])
    with pytest.raises(KeyError, match="no telemetry was logged at t = 0.2 s"):
        module.estimate_datasets(np.array([0.2]))
