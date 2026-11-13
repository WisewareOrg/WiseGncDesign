"""The F´ build of the dead reckoner against the notebook's, driven directly with no simulator.

Skipped without the deployment `just fsw` builds.
"""

from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from gnc_algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from gnc_cdh.dictionary import Dictionary
from gnc_cdh.fprime import DICTIONARY, extension

pytest.importorskip("gnc_cdh.fprime._wise_fsw", reason="the F´ build is absent; run `just fsw`")
_wise_fsw = extension()

MU = 3.986004360e14
"""m^3/s^2, Earth's gravitational parameter, as the scenarios set it."""

Q0 = Rotation.from_euler("zyx", [40.0, -25.0, 60.0], degrees=True).as_quat(scalar_first=True)
"""An attitude, quaternion W X Y Z of the body with respect to ECI, W >= 0."""
R0 = np.array([6871.0e3, 0.0, 0.0])
V0 = np.array([0.0, 5.4e3, 5.4e3])
MOUNTING = Rotation.from_euler("zyx", [10.0, -20.0, 30.0], degrees=True).as_matrix()
"""A mounting [PB] that is not the identity, so a transposed mounting shows."""

NS = 1_000_000_000
"""ns per s."""

WISE_FSW = Dictionary(DICTIONARY)
"""The deployment's dictionary, which the build generated."""


def _telemetry() -> dict[str, object]:
    """Drains the telemetry writes and keeps each channel's last, by name.

    Returns:
        Channel name, `<instance>.<channel>`, to its last value written since the previous drain.
    """
    channels = WISE_FSW.channels_by_id
    return {channels[i].name: channels[i].decode(raw) for i, _, raw in _wise_fsw.telemetry()}


def test_the_python_build_and_the_fprime_build_hold_nav_to_one_contract():
    """The Python build's dictionary, from the `.fpp` alone, states WiseFsw's nav, IDs aside.

    It also fails when the `.fpp` or a group it includes changed and F´ was not rebuilt.
    """
    model = [Path(__file__).with_name("ImuDeadReckoner.fpp")]
    python = Dictionary.from_component(model, "Gnc.ImuDeadReckoner", instance="nav")

    assert python.entries("nav")["channels"]
    assert python.entries("nav")["commands"]
    assert python.entries("nav") == WISE_FSW.entries("nav")


def _assert_matches(python: ImuDeadReckoner) -> None:
    """The deployment's latest telemetry is a propagated state that agrees with `python`'s.

    Args:
        python: the notebook's reckoner, stepped through the same readings.
    """
    tlm = _telemetry()
    assert tlm["nav.navState"] == "propagated"
    assert tlm["nav.bodyEciAttitude"][0] >= 0.0
    np.testing.assert_allclose(tlm["nav.bodyEciAttitude"], python.q_BN, rtol=0, atol=1e-12)
    np.testing.assert_allclose(tlm["nav.bodyEciPos"], python.r_BN_N, rtol=1e-12)
    np.testing.assert_allclose(tlm["nav.bodyEciVel"], python.v_BN_N, rtol=1e-12)


def test_a_booted_reckoner_reports_idle_and_no_state():
    """Booted, the deployment reports `navState` idle and writes no position."""
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert _telemetry() == {"nav.navState": "idle"}


@pytest.mark.parametrize("sign", [1.0, -1.0], ids=["w-positive", "w-negative"])
def test_initialization_writes_the_initial_quaternion_with_w_nonnegative(sign: float):
    """Initialized from q or -q, the deployment writes q, whose W is not negative.

    Args:
        sign: the sign the initial quaternion is given with.
    """
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, q_BN=sign * Q0, r_BN_N=R0, v_BN_N=V0)

    tlm = _telemetry()
    assert tlm["nav.navState"] == "initialized"
    np.testing.assert_array_equal(tlm["nav.bodyEciAttitude"], Q0)


@pytest.mark.parametrize(
    ("rate_rad_s", "step_ns"),
    [(0.02, NS), (0.5, NS), (0.02, NS // 10)],
    ids=["slow", "past-a-half-turn", "at-10-Hz"],
)
def test_the_fprime_build_matches_the_notebook_reading_for_reading(rate_rad_s: float, step_ns: int):
    """Fed the same 600 readings, the two builds agree to rounding.

    The faster rate turns the body past 180 degrees, so W changes sign and both flip q; the 10 Hz
    case ticks between whole seconds.

    Args:
        rate_rad_s: rad/s, the gyro reading's magnitude.
        step_ns: ns between readings.
    """
    rng = np.random.default_rng(7)
    readings = [(rate_rad_s * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(600)]
    python = ImuDeadReckoner(Q0, R0, V0, t0=0.0, mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, q_BN=Q0, r_BN_N=R0, v_BN_N=V0)

    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=k * step_ns / NS, AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t_ns=k * step_ns, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(python)


def test_init_nav_state_starts_the_reckoner_at_its_epoch():
    """Commanded with a state as of t = 60 s, the deployment agrees with a notebook started at 60 s.

    The command runs at the step to 61 s, which propagates from the epoch.
    """
    rng = np.random.default_rng(5)
    readings = [(0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(300)]
    python = ImuDeadReckoner(Q0, R0, V0, t0=60.0, mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    for k in range(1, 61):
        _wise_fsw.step(t_ns=k * NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
    state = {"epoch": 60.0, "attitude": Q0, "position": R0, "velocity": V0}
    _wise_fsw.uplink(WISE_FSW.encode_command("nav.initNavState", state), 1)

    for k, (omega, accel) in enumerate(readings, start=61):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    assert _wise_fsw.responses() == [(1, WISE_FSW.responses["OK"])]
    _assert_matches(python)


Q_B = Rotation.from_euler("zyx", [-70.0, 10.0, -35.0], degrees=True).as_quat(scalar_first=True)
R_B = np.array([7000.0e3, 100.0e3, -50.0e3])
V_B = np.array([-200.0, 5.0e3, 5.6e3])
"""A second flight's initial state, apart from `Q0`, `R0` and `V0` in every component."""


def _fly_a_first_flight() -> None:
    """Boots, initializes from the first state and steps to t = 600 s with nonzero readings."""
    rng = np.random.default_rng(3)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, q_BN=Q0, r_BN_N=R0, v_BN_N=V0)
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
    python = ImuDeadReckoner(Q_B, R_B, V_B, t0=0.0, mu=MU, dcm_PB=MOUNTING)

    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    _wise_fsw.initialize_nav(t_ns=0, q_BN=Q_B, r_BN_N=R_B, v_BN_N=V_B)
    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(python)
