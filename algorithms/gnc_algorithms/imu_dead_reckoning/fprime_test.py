"""The F´ build of the dead reckoner against the notebook's, driven directly with no simulator.

Needs the deployment `just fsw` builds.
"""

import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from gnc_algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from gnc_algorithms.mrp import dcm_NB
from gnc_cdh.fprime import DICTIONARY, _wise_fsw, decoders

MU = 3.986004360e14
"""m^3/s^2, Earth's gravitational parameter, as the scenarios set it."""

SIGMA0 = np.array([0.1, 0.2, -0.3])
R0 = np.array([6871.0e3, 0.0, 0.0])
V0 = np.array([0.0, 5.4e3, 5.4e3])
MOUNTING = Rotation.from_euler("zyx", [10.0, -20.0, 30.0], degrees=True).as_matrix()
"""A mounting [PB] that is not the identity, so a transposed mounting shows."""


def _telemetry() -> dict[str, object]:
    """The latest value of every channel, by name.

    Returns:
        Channel name, `<instance>.<channel>`, to its decoded value.
    """
    channels = decoders(json.loads(DICTIONARY.read_text()))
    return {
        channels[cid][0]: channels[cid][1](raw) for cid, (_, raw) in _wise_fsw.telemetry().items()
    }


def test_a_booted_reckoner_reports_idle_and_no_state():
    """Booted, the deployment reports `navState` idle and writes no position."""
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.step(t=1.0, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert _telemetry() == {"nav.navState": "idle"}


def test_the_attitude_quaternion_takes_body_vectors_into_eci_with_w_nonnegative():
    """The quaternion's matrix is [NB] of the initial MRP, and its W is not negative."""
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t=0.0, sigma_BN=SIGMA0, r_BN_N=R0, v_BN_N=V0)

    tlm = _telemetry()
    q = [tlm[f"nav.bodyEciAttitude{a}"] for a in "XYZW"]
    assert tlm["nav.navState"] == "initialized"
    assert q[3] >= 0.0
    np.testing.assert_allclose(Rotation.from_quat(q).as_matrix(), dcm_NB(SIGMA0), atol=1e-15)
    np.testing.assert_allclose(Rotation.from_quat(q).as_mrp(), SIGMA0, atol=1e-15)


@pytest.mark.parametrize("rate_rad_s", [0.02, 0.5], ids=["slow", "past-the-shadow-switch"])
def test_the_fprime_build_matches_the_notebook_reading_for_reading(rate_rad_s: float):
    """Fed the same readings at 1 Hz for 600 s, the two builds agree to rounding.

    The faster rate turns the body past 180 degrees, so both switch to the shadow set.

    Args:
        rate_rad_s: rad/s, the gyro reading's magnitude.
    """
    rng = np.random.default_rng(7)
    readings = [(rate_rad_s * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(600)]
    python = ImuDeadReckoner(SIGMA0, R0, V0, t0=0.0, mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t=0.0, sigma_BN=SIGMA0, r_BN_N=R0, v_BN_N=V0)

    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t=float(k), angVelPlatform=omega, accelPlatform=accel)

    tlm = _telemetry()
    q = [tlm[f"nav.bodyEciAttitude{a}"] for a in "XYZW"]
    assert tlm["nav.navState"] == "propagated"
    np.testing.assert_allclose(
        Rotation.from_quat(q).as_matrix(), dcm_NB(python.sigma_BN), atol=1e-12
    )
    np.testing.assert_allclose(
        [tlm[f"nav.bodyEciPos{a}"] for a in "XYZ"], python.r_BN_N, rtol=1e-12
    )
    np.testing.assert_allclose(
        [tlm[f"nav.bodyEciVel{a}"] for a in "XYZ"], python.v_BN_N, rtol=1e-12
    )
