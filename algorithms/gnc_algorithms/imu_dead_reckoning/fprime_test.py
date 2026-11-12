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

NS = 1_000_000_000
"""ns per s."""


def _telemetry() -> dict[str, object]:
    """The latest value of every channel, by name.

    Returns:
        Channel name, `<instance>.<channel>`, to its decoded value.
    """
    channels = decoders(json.loads(DICTIONARY.read_text()))
    return {
        channels[cid][0]: channels[cid][1](raw) for cid, (_, raw) in _wise_fsw.telemetry().items()
    }


def _assert_matches(python: ImuDeadReckoner) -> None:
    """The deployment's latest telemetry is a propagated state that agrees with `python`'s.

    Args:
        python: the notebook's reckoner, stepped through the same readings.
    """
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


def test_a_booted_reckoner_reports_idle_and_no_state():
    """Booted, the deployment reports `navState` idle and writes no position."""
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert _telemetry() == {"nav.navState": "idle"}


def test_the_attitude_quaternion_takes_body_vectors_into_eci_with_w_nonnegative():
    """The quaternion's matrix is [NB] of the initial MRP, and its W is not negative."""
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, sigma_BN=SIGMA0, r_BN_N=R0, v_BN_N=V0)

    tlm = _telemetry()
    q = [tlm[f"nav.bodyEciAttitude{a}"] for a in "XYZW"]
    assert tlm["nav.navState"] == "initialized"
    assert q[3] >= 0.0
    np.testing.assert_allclose(Rotation.from_quat(q).as_matrix(), dcm_NB(SIGMA0), atol=1e-15)
    np.testing.assert_allclose(Rotation.from_quat(q).as_mrp(), SIGMA0, atol=1e-15)


@pytest.mark.parametrize(
    ("rate_rad_s", "step_ns"),
    [(0.02, NS), (0.5, NS), (0.02, NS // 10)],
    ids=["slow", "past-the-shadow-switch", "at-10-Hz"],
)
def test_the_fprime_build_matches_the_notebook_reading_for_reading(rate_rad_s: float, step_ns: int):
    """Fed the same 600 readings, the two builds agree to rounding.

    The faster rate turns the body past 180 degrees, so both switch to the shadow set; the 10 Hz
    case ticks between whole seconds.

    Args:
        rate_rad_s: rad/s, the gyro reading's magnitude.
        step_ns: ns between readings.
    """
    rng = np.random.default_rng(7)
    readings = [(rate_rad_s * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(600)]
    python = ImuDeadReckoner(SIGMA0, R0, V0, t0=0.0, mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, sigma_BN=SIGMA0, r_BN_N=R0, v_BN_N=V0)

    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=k * step_ns / NS, AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t_ns=k * step_ns, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(python)


SIGMA_B = np.array([-0.2, 0.05, 0.4])
R_B = np.array([7000.0e3, 100.0e3, -50.0e3])
V_B = np.array([-200.0, 5.0e3, 5.6e3])
"""A second flight's initial state, apart from `SIGMA0`, `R0` and `V0` in every component."""


def _fly_a_first_flight() -> None:
    """Boots, initializes from the first state and steps to t = 600 s with nonzero readings."""
    rng = np.random.default_rng(3)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, sigma_BN=SIGMA0, r_BN_N=R0, v_BN_N=V0)
    for k in range(1, 61):
        _wise_fsw.step(
            t_ns=10 * k * NS,
            angVelPlatform=0.02 * rng.normal(size=3),
            accelPlatform=1e-3 * rng.normal(size=3),
        )
    assert _telemetry()["nav.navState"] == "propagated"


def test_a_rebooted_reckoner_keeps_nothing_of_the_previous_flight():
    """After a flight, booting again leaves the reckoner idle, with no state, from t = 0."""
    _fly_a_first_flight()

    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert _telemetry() == {"nav.navState": "idle"}


def test_a_second_flight_matches_a_fresh_notebook_reckoner():
    """A flight after another, from its own state, agrees with a reckoner that never flew before."""
    _fly_a_first_flight()
    rng = np.random.default_rng(11)
    readings = [(0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(300)]
    python = ImuDeadReckoner(SIGMA_B, R_B, V_B, t0=0.0, mu=MU, dcm_PB=MOUNTING)

    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, sigma_BN=SIGMA_B, r_BN_N=R_B, v_BN_N=V_B)
    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(python)
