"""The F´ build of the dead reckoner against the notebook's, driven directly with no simulator.

One test drives it through the F´ host, `lab.FprimeModule`, on Basilisk's IMU message. Skipped
without the deployment `just fsw` builds.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from Basilisk.architecture import messaging
from scipy.spatial.transform import Rotation

from algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from fsw.codegen.deployment import fpp_files
from fsw.codegen.fpp_model import read
from fsw.codegen.fpp_types import Gnc
from ground.fprime_station import FprimeStation
from lab import FprimeModule

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

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

NAV = Gnc.ImuDeadReckonerParameters(mu=MU, dcm_PB=MOUNTING)
"""Nav's parameters."""


@pytest.fixture
def nav_parameters() -> Gnc.ImuDeadReckonerParameters:
    """The case's parameters for this module: `NAV`, its mounting not the identity.

    Returns:
        `NAV`.
    """
    return NAV


def _telemetry(station: FprimeStation) -> dict[str, object]:
    """Drains the telemetry writes and keeps each of nav's channels' last, by name.

    Args:
        station: the station on the copy.

    Returns:
        Channel name, `nav.<channel>`, to its last value written since the previous drain.
    """
    writes = station.telemetry()
    return {
        name: station.values(name, [raw])[0] for name, _, raw in writes if name.startswith("nav.")
    }


def _assert_matches(station: FprimeStation, python: ImuDeadReckoner) -> None:
    """The copy's latest telemetry is a propagated state that agrees with `python`'s.

    Args:
        station: the station on the copy.
        python: the notebook's reckoner, stepped through the same readings.
    """
    tlm = _telemetry(station)
    assert tlm["nav.navState"] == "propagated"
    assert tlm["nav.bodyEciAttitude"][0] >= 0.0
    np.testing.assert_allclose(tlm["nav.bodyEciAttitude"], python.q_BN, rtol=0, atol=1e-12)
    np.testing.assert_allclose(tlm["nav.bodyEciPos"], python.r_BN_N, rtol=1e-12)
    np.testing.assert_allclose(tlm["nav.bodyEciVel"], python.v_BN_N, rtol=1e-12)


def test_a_booted_reckoner_reports_idle_and_no_state(
    fsw: ModuleType, station: FprimeStation, prm: str, parameter_ids: list[int]
):
    """Booted, the deployment reports `navState` idle and writes no position.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    fsw.boot(prm, parameter_ids)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert _telemetry(station) == {"nav.navState": "idle"}


@pytest.mark.parametrize("sign", [1.0, -1.0], ids=["w-positive", "w-negative"])
def test_initialization_writes_the_initial_quaternion_with_w_nonnegative(
    fsw: ModuleType,
    station: FprimeStation,
    sign: float,
    prm: str,
    parameter_ids: list[int],
):
    """Commanded q or -q as of t = 0 and stepped 1 s at zero rate, the deployment writes q.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        sign: the sign the initial quaternion is given with.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    fsw.boot(prm, parameter_ids)
    state = {"epoch": 0.0, "attitude": sign * Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    np.testing.assert_allclose(_telemetry(station)["nav.bodyEciAttitude"], Q0, rtol=0, atol=1e-15)


@pytest.mark.parametrize(
    ("rate_rad_s", "step_ns"),
    [(0.02, NS), (0.5, NS), (0.02, NS // 10)],
    ids=["slow", "past-a-half-turn", "at-10-Hz"],
)
def test_the_fprime_build_matches_the_notebook_reading_for_reading(
    fsw: ModuleType,
    station: FprimeStation,
    rate_rad_s: float,
    step_ns: int,
    prm: str,
    parameter_ids: list[int],
):
    """Fed the same 600 readings, the two builds agree to rounding.

    The faster rate turns the body past 180 degrees, so W changes sign and both flip q; the 10 Hz
    case ticks between whole seconds.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        rate_rad_s: rad/s, the gyro reading's magnitude.
        step_ns: ns between readings.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    rng = np.random.default_rng(7)
    readings = [(rate_rad_s * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(600)]
    python = ImuDeadReckoner(NAV)
    python.initNavState(epoch=0.0, attitude=Q0, position=R0, velocity=V0)
    fsw.boot(prm, parameter_ids)
    state = {"epoch": 0.0, "attitude": Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)

    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=k * step_ns / NS, AngVelPlatform=omega, AccelPlatform=accel)
        fsw.step(t_ns=k * step_ns, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(station, python)


def test_init_nav_state_starts_the_reckoner_at_its_epoch(
    fsw: ModuleType, station: FprimeStation, prm: str, parameter_ids: list[int]
):
    """Commanded with a state as of t = 60 s, the deployment agrees with a notebook started at 60 s.

    The command runs at the step to 61 s, which propagates from the epoch.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    rng = np.random.default_rng(5)
    readings = [(0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(300)]
    python = ImuDeadReckoner(NAV)
    python.initNavState(epoch=60.0, attitude=Q0, position=R0, velocity=V0)
    fsw.boot(prm, parameter_ids)
    for k in range(1, 61):
        fsw.step(t_ns=k * NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
    state = {"epoch": 60.0, "attitude": Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)

    for k, (omega, accel) in enumerate(readings, start=61):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    assert station.responses() == [(1, "OK", None)]
    _assert_matches(station, python)


def test_one_scheduled_run_writes_nav_state_once(
    fsw: ModuleType,
    station: FprimeStation,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
):
    """Over `navDivider` ticks the rate group runs nav once, and nav writes `navState` once.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        tmp_path: where the deployment's topology is rendered.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    divider = read(fpp_files("ImuDeadReckoning", tmp_path)).constants["ImuDeadReckoning.navDivider"]
    fsw.boot(prm, parameter_ids)
    station.telemetry()

    for tick in range(1, divider + 1):
        fsw.step(t_ns=tick * NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    writes = [name for name, _, _ in station.telemetry() if name == "nav.navState"]
    assert writes == ["nav.navState"]


@pytest.mark.parametrize("nav_parameters", [NAV._replace(mu=4.9048695e12)], ids=["moon"])
def test_the_fprime_build_flies_the_mu_its_record_gives(
    fsw: ModuleType,
    station: FprimeStation,
    nav_parameters: Gnc.ImuDeadReckonerParameters,
    prm: str,
    parameter_ids: list[int],
):
    """Booted on a record with the Moon's mu, nav propagates as the notebook does on that mu.

    Earth's mu differs by a factor of 81, so a nav flying any other mu than the record's fails.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        nav_parameters: `NAV` with the Moon's mu.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    fsw.boot(prm, parameter_ids)
    python = ImuDeadReckoner(nav_parameters)
    python.initNavState(epoch=0.0, attitude=Q0, position=R0, velocity=V0)
    state = {"epoch": 0.0, "attitude": Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)
    rng = np.random.default_rng(13)

    for k in range(1, 61):
        omega, accel = 0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(station, python)


def test_the_f_prime_host_mounts_the_imu_as_its_record_gives_it(
    nav_parameters: Gnc.ImuDeadReckonerParameters, prm_record: Path
):
    """On `NAV`'s mounting, which is not the identity, the F´ host's estimate is the notebook's.

    Ten readings are enough for a transposed mounting to show far above rounding.

    Args:
        nav_parameters: `NAV`.
        prm_record: the case's parameter record.
    """
    state = {
        "epoch": 0.0,
        "attitude": [1.0, 0.0, 0.0, 0.0],
        "position": [6871.0e3, 0.0, 0.0],
        "velocity": [0.0, 5.4e3, 5.4e3],
    }
    module = FprimeModule(messaging.IMUSensorMsgReader(), prm_record)
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)
    module.uplink("nav.initNavState", state, 1)
    python = ImuDeadReckoner(nav_parameters)
    python.initNavState(**state)
    rng = np.random.default_rng(7)

    for k in range(1, 11):
        reading = messaging.IMUSensorMsgPayload()
        reading.AngVelPlatform = (0.02 * rng.normal(size=3)).tolist()
        reading.AccelPlatform = (1e-3 * rng.normal(size=3)).tolist()
        imu.write(reading, k * NS, 0)
        module.UpdateState(k * NS)
        python.step(
            t=float(k),
            AngVelPlatform=np.array(reading.AngVelPlatform),
            AccelPlatform=np.array(reading.AccelPlatform),
        )

    latest = {name: module.values(name, [raw])[0] for name, _, raw in module.telemetry()}
    np.testing.assert_allclose(latest["nav.bodyEciAttitude"], python.q_BN, rtol=0, atol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciPos"], python.r_BN_N, rtol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciVel"], python.v_BN_N, rtol=1e-12)
