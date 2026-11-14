"""The F´ build of the dead reckoner against the notebook's, driven directly with no simulator.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from fsw.codegen.deployment import fpp_files
from fsw.codegen.fpp_model import read
from fsw.codegen.fpp_types import Gnc
from fsw.python.cdh import parameters as cdh_parameters
from ground import parameters
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY
from lab.power_cycle import power_cycle

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

WISE_FSW = Dictionary(DICTIONARY)
"""The deployment's dictionary, which the build generated."""


@pytest.fixture
def fsw() -> ModuleType:
    """A fresh copy of the deployment, not yet booted.

    Returns:
        The copy.
    """
    return power_cycle()


@pytest.fixture
def nav_parameters() -> Gnc.ImuDeadReckonerParameters:
    """The case's parameters for this module: `NAV`, its mounting not the identity.

    Returns:
        `NAV`.
    """
    return NAV


@pytest.fixture
def station(fsw: ModuleType) -> FprimeStation:
    """The ground station on the test's copy.

    Args:
        fsw: the test's copy.

    Returns:
        The station.
    """
    return FprimeStation(fsw, WISE_FSW)


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


def test_the_python_build_and_the_fprime_build_hold_nav_to_one_contract():
    """The Python build's dictionary, from the `.fpp` alone, states WiseFsw's nav, IDs aside.

    It also fails when the `.fpp` or a group it includes changed and F´ was not rebuilt.
    """
    model = [Path(__file__).with_name("ImuDeadReckoner.fpp")]
    python = Dictionary.from_component(model, "Gnc.ImuDeadReckoner", instance="nav")

    assert python.entries("nav")["channels"]
    assert python.entries("nav")["commands"]
    assert python.entries("nav") == WISE_FSW.entries("nav")


def test_the_python_build_numbers_nav_s_parameters_as_the_fprime_build_does():
    """Nav's parameters have the same IDs in the Python build's dictionary as in WiseFsw's."""
    model = [Path(__file__).with_name("ImuDeadReckoner.fpp")]
    python = Dictionary.from_component(model, "Gnc.ImuDeadReckoner", instance="nav")

    def ids(dictionary: Dictionary) -> dict[str, int]:
        """Each of nav's parameters' ID.

        Args:
            dictionary: a dictionary.

        Returns:
            ID by `nav.<parameter>`.
        """
        named = dictionary.parameters_by_id.values()
        return {p.name: p.id for p in named if p.name.startswith("nav.")}

    assert ids(python) == {"nav.mu": 0x1000, "nav.dcm_PB": 0x1001}
    assert ids(python) == ids(WISE_FSW)


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


Q_B = Rotation.from_euler("zyx", [-70.0, 10.0, -35.0], degrees=True).as_quat(scalar_first=True)
R_B = np.array([7000.0e3, 100.0e3, -50.0e3])
V_B = np.array([-200.0, 5.0e3, 5.6e3])
"""A second flight's initial state, apart from `Q0`, `R0` and `V0` in every component."""


def _fly_a_first_flight(prm: str, parameter_ids: list[int]) -> None:
    """On a copy of its own: boots, commands the first state, steps to 600 s on nonzero readings.

    Args:
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    rng = np.random.default_rng(3)
    first = power_cycle()
    station = FprimeStation(first, WISE_FSW)
    first.boot(prm, parameter_ids)
    state = {"epoch": 0.0, "attitude": Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)
    for k in range(1, 61):
        first.step(
            t_ns=10 * k * NS,
            angVelPlatform=0.02 * rng.normal(size=3),
            accelPlatform=1e-3 * rng.normal(size=3),
        )
    assert _telemetry(station)["nav.navState"] == "propagated"


def test_a_fresh_copy_after_another_copy_flew_keeps_nothing_of_that_flight(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
    parameter_ids: list[int],
):
    """After a flight, a fresh copy boots the reckoner idle, with no state, from t = 0.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    _fly_a_first_flight(prm, parameter_ids)

    fsw.boot(prm, parameter_ids)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert _telemetry(station) == {"nav.navState": "idle"}


def test_the_fprime_build_runs_nav_once_every_nav_divider_ticks(
    fsw: ModuleType,
    station: FprimeStation,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
):
    """Nav writes its state once per run, so `10 * navDivider` ticks give exactly 10 writes.

    The count is taken over a whole number of dividers, which holds whatever tick the driver
    starts on.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        tmp_path: where the deployment's topology is rendered.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    divider = read(fpp_files("ImuDeadReckoning", tmp_path)).constants["ImuDeadReckoning.navDivider"]
    ticks = 10 * divider
    fsw.boot(prm, parameter_ids)
    station.telemetry()

    for tick in range(1, ticks + 1):
        fsw.step(t_ns=tick * NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    writes = [name for name, _, _ in station.telemetry() if name == "nav.navState"]
    assert len(writes) == ticks // divider


def test_a_flight_on_a_fresh_copy_after_another_copy_flew_matches_a_fresh_notebook_reckoner(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
    parameter_ids: list[int],
):
    """A fresh copy's flight after another copy's agrees with a reckoner that never flew before.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    _fly_a_first_flight(prm, parameter_ids)
    rng = np.random.default_rng(11)
    readings = [(0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(300)]
    python = ImuDeadReckoner(NAV)
    python.initNavState(epoch=0.0, attitude=Q_B, position=R_B, velocity=V_B)

    fsw.boot(prm, parameter_ids)
    state = {"epoch": 0.0, "attitude": Q_B, "position": R_B, "velocity": V_B}
    station.uplink("nav.initNavState", state, 1)
    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=float(k), AngVelPlatform=omega, AccelPlatform=accel)
        fsw.step(t_ns=k * NS, angVelPlatform=omega, accelPlatform=accel)

    _assert_matches(station, python)


def test_a_value_changed_in_the_record_reaches_prm_db_and_the_python_build_alike(
    fsw: ModuleType,
    station: FprimeStation,
    tmp_path: Path,
    prm_record: Path,
    parameter_ids: list[int],
):
    """`mu` edited in the record is the one the F´ build's PrmDb holds and the Python build reads.

    PrmDb's own image comes back through `PRM_SAVE_FILE`, which rewrites the `.dat`, and F´'s
    `fprime-prm-decode`, always given `-o` since it would otherwise overwrite the record.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        tmp_path: where PrmDb's image is decoded.
        prm_record: the case's parameter record, edited here.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    record = prm_record
    entries = json.loads(record.read_text())
    entries["ImuDeadReckoning.nav"]["mu"] = 4.9048695e12
    record.write_text(json.dumps(entries))
    dat = parameters.dat(record, DICTIONARY)
    fsw.boot(str(dat), parameter_ids)

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 1)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
    decoded = tmp_path / "decoded.json"
    tool = Path(sys.executable).parent / "fprime-prm-decode"
    subprocess.run([tool, dat, "-d", DICTIONARY, "-o", decoded], check=True, capture_output=True)

    assert station.responses() == [(1, "OK", None)]
    assert json.loads(decoded.read_text())["ImuDeadReckoning.nav"]["mu"] == 4.9048695e12
    python = cdh_parameters.read(record, Gnc.ImuDeadReckonerParameters)
    assert python.mu == 4.9048695e12
    assert json.loads(decoded.read_text()) == json.loads(record.read_text())


def test_a_parameter_missing_from_the_record_fails_both_builds(
    fsw: ModuleType, prm_record: Path, parameter_ids: list[int]
):
    """Without `mu` in the record, the F´ build's boot and the Python build's read both raise.

    Args:
        fsw: the test's copy of the deployment.
        prm_record: the case's parameter record, edited here.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    record = prm_record
    entries = json.loads(record.read_text())
    del entries["ImuDeadReckoning.nav"]["mu"]
    record.write_text(json.dumps(entries))
    mu = next(i for i, p in WISE_FSW.parameters_by_id.items() if p.name == "nav.mu")

    with pytest.raises(RuntimeError, match=rf"^parameters {mu} are not valid"):
        fsw.boot(str(parameters.dat(record, DICTIONARY)), parameter_ids)
    with pytest.raises(TypeError, match="mu"):
        cdh_parameters.read(record, Gnc.ImuDeadReckonerParameters)


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
