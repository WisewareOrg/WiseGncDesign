"""The F´ build of the dead reckoner against the notebook's, driven directly with no simulator.

Skipped without the deployment `just fsw` builds.
"""

from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from fsw.codegen.deployment import FPP_FILES
from fsw.codegen.fpp_model import read
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY, extension

pytest.importorskip("lab._wise_fsw", reason="the F´ build is absent; run `just fsw`")
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

STATION = FprimeStation(_wise_fsw, WISE_FSW)
"""The ground station on the deployment."""


def _telemetry() -> dict[str, object]:
    """Drains the telemetry writes and keeps each of nav's channels' last, by name.

    Returns:
        Channel name, `nav.<channel>`, to its last value written since the previous drain.
    """
    writes = STATION.telemetry()
    return {
        name: STATION.values(name, [raw])[0] for name, _, raw in writes if name.startswith("nav.")
    }


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
    """Commanded q or -q as of t = 0 and stepped 1 s at zero rate, the deployment writes q.

    Args:
        sign: the sign the initial quaternion is given with.
    """
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    state = {"epoch": 0.0, "attitude": sign * Q0, "position": R0, "velocity": V0}
    STATION.uplink("nav.initNavState", state, 1)
    _wise_fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    np.testing.assert_allclose(_telemetry()["nav.bodyEciAttitude"], Q0, rtol=0, atol=1e-15)


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
    python = ImuDeadReckoner(mu=MU, dcm_PB=MOUNTING)
    python.initNavState(epoch=0.0, attitude=Q0, position=R0, velocity=V0)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    state = {"epoch": 0.0, "attitude": Q0, "position": R0, "velocity": V0}
    STATION.uplink("nav.initNavState", state, 1)

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
    python = ImuDeadReckoner(mu=MU, dcm_PB=MOUNTING)
    python.initNavState(epoch=60.0, attitude=Q0, position=R0, velocity=V0)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    for k in range(1, 61):
        _wise_fsw.step(t_ns=k * NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
    state = {"epoch": 60.0, "attitude": Q0, "position": R0, "velocity": V0}
    STATION.uplink("nav.initNavState", state, 1)

    for k, (omega, accel) in enumerate(readings, start=61):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    assert STATION.responses() == [(1, "OK", None)]
    _assert_matches(python)


Q_B = Rotation.from_euler("zyx", [-70.0, 10.0, -35.0], degrees=True).as_quat(scalar_first=True)
R_B = np.array([7000.0e3, 100.0e3, -50.0e3])
V_B = np.array([-200.0, 5.0e3, 5.6e3])
"""A second flight's initial state, apart from `Q0`, `R0` and `V0` in every component."""


def _fly_a_first_flight() -> None:
    """Boots, commands the first state and steps to t = 600 s with nonzero readings."""
    rng = np.random.default_rng(3)
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    state = {"epoch": 0.0, "attitude": Q0, "position": R0, "velocity": V0}
    STATION.uplink("nav.initNavState", state, 1)
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


def test_the_fprime_build_runs_nav_once_every_nav_divider_ticks():
    """Nav writes its state once per run, so `10 * navDivider` ticks give exactly 10 writes.

    The driver's tick count carries over from earlier tests in the process, so the count is taken
    over a whole number of dividers, which holds whatever tick the driver starts on.
    """
    divider = read(FPP_FILES).constants["ImuDeadReckoning.navDivider"]
    ticks = 10 * divider
    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    STATION.telemetry()

    for tick in range(1, ticks + 1):
        _wise_fsw.step(t_ns=tick * NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    writes = [name for name, _, _ in STATION.telemetry() if name == "nav.navState"]
    assert len(writes) == ticks // divider


def test_a_second_flight_matches_a_fresh_notebook_reckoner():
    """A flight after another, from its own state, agrees with a reckoner that never flew before."""
    _fly_a_first_flight()
    rng = np.random.default_rng(11)
    readings = [(0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(300)]
    python = ImuDeadReckoner(mu=MU, dcm_PB=MOUNTING)
    python.initNavState(epoch=0.0, attitude=Q_B, position=R_B, velocity=V_B)

    _wise_fsw.boot(mu=MU, dcm_PB=MOUNTING)
    state = {"epoch": 0.0, "attitude": Q_B, "position": R_B, "velocity": V_B}
    STATION.uplink("nav.initNavState", state, 1)
    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        _wise_fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(python)
