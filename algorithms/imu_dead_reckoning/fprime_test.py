"""The F´ build of the dead reckoner against the notebook's, driven directly with no simulator.

One test drives it through the F´ host, `lab.FprimeModule`, on Basilisk's IMU message. Skipped
without the deployment `just fsw` builds.
"""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from Basilisk.architecture import messaging
from scipy.spatial.transform import Rotation

from algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from fsw.codegen.deployment import bus_port, contract_files, fpp_files
from fsw.codegen.fpp_model import read
from fsw.codegen.fpp_types import Gnc
from fsw.codegen.roles import roles
from ground.fprime_station import FprimeStation
from lab import FprimeModule
from lab.bus_emulator import serialize

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
    """Nav's parameters for this module's cases: `NAV`, its mounting not the identity.

    Returns:
        `NAV`.
    """
    return NAV


@pytest.fixture
def case_parameters(
    case_parameters: tuple[Any, ...], nav_parameters: Gnc.ImuDeadReckonerParameters
) -> tuple[Any, ...]:
    """The deployment's case parameters, nav's tuple replaced by `nav_parameters`.

    Args:
        case_parameters: the deployment's, each zero, as the root conftest gives them.
        nav_parameters: nav's parameters.

    Returns:
        The tuples.
    """
    return tuple(nav_parameters if type(t) is type(nav_parameters) else t for t in case_parameters)


@pytest.fixture(scope="module")
def imu_bus() -> Callable[[Any, Any], list[tuple[int, bytes]]]:
    """The bus a step takes for one IMU reading: nav's role's message bytes on its SimHub port.

    The role is the contract's `Cdh.BusConverter` role whose GNC struct nav's `imuIn` takes, and
    its port the one the configuration's deployment wires to the role's CDH input.

    Returns:
        A function of the angular velocity and the acceleration, each three values in the
        platform frame, giving `[(port, bytes)]`, the message's dv and dr zero.
    """
    model = read(contract_files())
    [imu_in] = [p for p in model.components["Gnc.ImuDeadReckoner"].inputs if p.name == "imuIn"]
    [role] = [r for r in roles(model) if r.icd == imu_in.args[0].type]
    port = bus_port("ImuDeadReckoning", role.input)

    def bus(angVelPlatform: Any, accelPlatform: Any) -> list[tuple[int, bytes]]:
        """The bus for one reading.

        Args:
            angVelPlatform: rad/s, the angular velocity in the platform frame.
            accelPlatform: m/s2, the acceleration in the platform frame.

        Returns:
            `[(port, bytes)]`.
        """
        message = messaging.IMUSensorMsgPayload()
        message.AngVelPlatform = list(angVelPlatform)
        message.AccelPlatform = list(accelPlatform)
        return [(port, serialize(message))]

    return bus


def _latest(writes: list[tuple[str, int, Any]]) -> dict[str, Any]:
    """Each of nav's channels' last value among drained writes.

    Args:
        writes: drained writes, as `decoded` gives them.

    Returns:
        Channel name, `nav.<channel>`, to its last value.
    """
    return {name: value for name, _, value in writes if name.startswith("nav.")}


def _assert_matches(tlm: dict[str, Any], python: ImuDeadReckoner) -> None:
    """The copy's latest telemetry is a propagated state that agrees with `python`'s.

    Args:
        tlm: nav's latest telemetry, as `_latest` gives it.
        python: the notebook's reckoner, stepped through the same readings.
    """
    assert tlm["nav.navState"] == "propagated"
    assert tlm["nav.bodyEciAttitude"][0] >= 0.0
    np.testing.assert_allclose(tlm["nav.bodyEciAttitude"], python.q_BN, rtol=0, atol=1e-12)
    np.testing.assert_allclose(tlm["nav.bodyEciPos"], python.r_BN_N, rtol=1e-12)
    np.testing.assert_allclose(tlm["nav.bodyEciVel"], python.v_BN_N, rtol=1e-12)


def test_a_booted_reckoner_reports_idle_and_no_state(
    fsw: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    prm: str,
    parameter_ids: list[int],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Booted, the deployment reports `navState` idle and writes no position.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_bus: the IMU message's bus for a reading.
    """
    fsw.boot(prm, parameter_ids)
    fsw.step(t_ns=NS, bus=imu_bus(np.zeros(3), np.zeros(3)))

    assert _latest(decoded(station)) == {"nav.navState": "idle"}


@pytest.mark.parametrize("sign", [1.0, -1.0], ids=["w-positive", "w-negative"])
def test_initialization_writes_the_initial_quaternion_with_w_nonnegative(
    fsw: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    sign: float,
    prm: str,
    parameter_ids: list[int],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Commanded q or -q as of t = 0 and stepped 1 s at zero rate, the deployment writes q.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        sign: the sign the initial quaternion is given with.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_bus: the IMU message's bus for a reading.
    """
    fsw.boot(prm, parameter_ids)
    state = {"epoch": 0.0, "attitude": sign * Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)
    fsw.step(t_ns=NS, bus=imu_bus(np.zeros(3), np.zeros(3)))

    attitude = _latest(decoded(station))["nav.bodyEciAttitude"]
    np.testing.assert_allclose(attitude, Q0, rtol=0, atol=1e-15)


@pytest.mark.parametrize(
    ("rate_rad_s", "step_ns"),
    [(0.02, NS), (0.5, NS), (0.02, NS // 10)],
    ids=["slow", "past-a-half-turn", "at-10-Hz"],
)
def test_the_fprime_build_matches_the_notebook_reading_for_reading(
    fsw: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    rate_rad_s: float,
    step_ns: int,
    prm: str,
    parameter_ids: list[int],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Fed the same 600 readings, the two builds agree to rounding.

    The faster rate turns the body past 180 degrees, so W changes sign and both flip q; the 10 Hz
    case ticks between whole seconds.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        rate_rad_s: rad/s, the gyro reading's magnitude.
        step_ns: ns between readings.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_bus: the IMU message's bus for a reading.
    """
    rng = np.random.default_rng(7)
    readings = [(rate_rad_s * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(600)]
    python = ImuDeadReckoner(NAV)
    python.initNavState(epoch=0.0, attitude=Q0, position=R0, velocity=V0)
    fsw.boot(prm, parameter_ids)
    state = {"epoch": 0.0, "attitude": Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)

    for k, (omega, accel) in enumerate(readings, start=1):
        python.step(t=k * step_ns / NS, imu=Gnc.ImuReading(omega, accel))
        fsw.step(t_ns=k * step_ns, bus=imu_bus(omega, accel))

    _assert_matches(_latest(decoded(station)), python)


def test_init_nav_state_starts_the_reckoner_at_its_epoch(
    fsw: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    prm: str,
    parameter_ids: list[int],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Commanded with a state as of t = 60 s, the deployment agrees with a notebook started at 60 s.

    The command runs at the step to 61 s, which propagates from the epoch.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_bus: the IMU message's bus for a reading.
    """
    rng = np.random.default_rng(5)
    readings = [(0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(300)]
    python = ImuDeadReckoner(NAV)
    python.initNavState(epoch=60.0, attitude=Q0, position=R0, velocity=V0)
    fsw.boot(prm, parameter_ids)
    for k in range(1, 61):
        fsw.step(t_ns=k * NS, bus=imu_bus(np.zeros(3), np.zeros(3)))
    state = {"epoch": 60.0, "attitude": Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)

    for k, (omega, accel) in enumerate(readings, start=61):
        python.step(t=float(k), imu=Gnc.ImuReading(omega, accel))
        fsw.step(t_ns=k * NS, bus=imu_bus(omega, accel))

    assert station.responses() == [(1, "OK", None)]
    _assert_matches(_latest(decoded(station)), python)


def test_one_scheduled_run_writes_nav_state_once(
    fsw: ModuleType,
    station: FprimeStation,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Over `navDivider` ticks the rate group runs nav once, and nav writes `navState` once.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        tmp_path: where the deployment's topology is rendered.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_bus: the IMU message's bus for a reading.
    """
    divider = read(fpp_files("ImuDeadReckoning", tmp_path)).constants["ImuDeadReckoning.navDivider"]
    fsw.boot(prm, parameter_ids)
    station.telemetry()

    for tick in range(1, divider + 1):
        fsw.step(t_ns=tick * NS, bus=imu_bus(np.zeros(3), np.zeros(3)))

    writes = [name for name, _, _ in station.telemetry() if name == "nav.navState"]
    assert writes == ["nav.navState"]


@pytest.mark.parametrize("nav_parameters", [NAV._replace(mu=4.9048695e12)], ids=["moon"])
def test_the_fprime_build_flies_the_mu_its_record_gives(
    fsw: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    nav_parameters: Gnc.ImuDeadReckonerParameters,
    prm: str,
    parameter_ids: list[int],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Booted on a record with the Moon's mu, nav propagates as the notebook does on that mu.

    Earth's mu differs by a factor of 81, so a nav flying any other mu than the record's fails.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        nav_parameters: `NAV` with the Moon's mu.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_bus: the IMU message's bus for a reading.
    """
    fsw.boot(prm, parameter_ids)
    python = ImuDeadReckoner(nav_parameters)
    python.initNavState(epoch=0.0, attitude=Q0, position=R0, velocity=V0)
    state = {"epoch": 0.0, "attitude": Q0, "position": R0, "velocity": V0}
    station.uplink("nav.initNavState", state, 1)
    rng = np.random.default_rng(13)

    for k in range(1, 61):
        omega, accel = 0.02 * rng.normal(size=3), 1e-3 * rng.normal(size=3)
        python.step(t=float(k), imu=Gnc.ImuReading(omega, accel))
        fsw.step(t_ns=k * NS, bus=imu_bus(omega, accel))

    _assert_matches(_latest(decoded(station)), python)


def test_the_f_prime_host_mounts_the_imu_as_its_record_gives_it(
    nav_parameters: Gnc.ImuDeadReckonerParameters,
    prm_record: Path,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
):
    """On `NAV`'s mounting, which is not the identity, the F´ host's estimate is the notebook's.

    Ten readings are enough for a transposed mounting to show far above rounding.

    Args:
        nav_parameters: `NAV`.
        prm_record: the case's parameter record.
        decoded: drains the host's telemetry as values.
    """
    state = {
        "epoch": 0.0,
        "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
        "position": R0,
        "velocity": V0,
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
            imu=Gnc.ImuReading(np.array(reading.AngVelPlatform), np.array(reading.AccelPlatform)),
        )

    latest = _latest(decoded(module))
    np.testing.assert_allclose(latest["nav.bodyEciAttitude"], python.q_BN, rtol=0, atol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciPos"], python.r_BN_N, rtol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciVel"], python.v_BN_N, rtol=1e-12)
