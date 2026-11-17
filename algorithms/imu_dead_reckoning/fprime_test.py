"""The F´ build of the dead reckoner against the notebook's, and its mission flown twice.

One test drives it through the lab adapter, `lab.Adapter`, on Basilisk's IMU message, and one flies
the dead reckoner's mission twice, in processes of their own, to hold that no case carries over to
the next. Skipped without the deployment `just fsw` builds.
"""

import importlib.util
import shutil
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import h5py
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
from lab import Adapter
from lab.bus_emulator import serialize

if importlib.util.find_spec("lab._wise_fsw_ImuDeadReckoning") is None:
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


@pytest.fixture(scope="session")
def configuration() -> str:
    """The dead reckoner's configuration, the only one this module's cases fly.

    Returns:
        `ImuDeadReckoning`.
    """
    return "ImuDeadReckoning"


@pytest.fixture
def nav_parameters() -> Gnc.ImuDeadReckonerParameters:
    """Nav's parameters for this module's cases: `NAV`, its mounting not the identity.

    Returns:
        `NAV`.
    """
    return NAV


@pytest.fixture
def case_parameters(
    case_parameters: dict[str, Any], nav_parameters: Gnc.ImuDeadReckonerParameters
) -> dict[str, Any]:
    """The deployment's case parameters, nav's tuple replaced by `nav_parameters`.

    Args:
        case_parameters: the deployment's, each zero, as the root conftest gives them.
        nav_parameters: nav's parameters.

    Returns:
        Each instance's tuple, by its qualified name.
    """
    return {
        instance: nav_parameters if type(t) is type(nav_parameters) else t
        for instance, t in case_parameters.items()
    }


@pytest.fixture(scope="module")
def imu_bus() -> Callable[[Any, Any], list[tuple[int, bytes]]]:
    """One IMU reading's bus for a step: nav's role's message bytes on its LabBusDriver port.

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


def test_the_lab_adapter_mounts_the_imu_as_its_record_gives_it(
    configuration: str,
    nav_parameters: Gnc.ImuDeadReckonerParameters,
    prm_record: Path,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
):
    """On `NAV`'s mounting, which is not the identity, the adapter's estimate is the notebook's.

    Ten readings are enough for a transposed mounting to show far above rounding.

    Args:
        configuration: the dead reckoner's configuration.
        nav_parameters: `NAV`.
        prm_record: the case's parameter record.
        decoded: drains the station's telemetry as values.
    """
    state = {
        "epoch": 0.0,
        "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
        "position": R0,
        "velocity": V0,
    }
    adapter = Adapter(configuration, prm_record)
    station = FprimeStation(adapter, adapter.dictionary)
    adapter.boot()
    station.uplink("nav.initNavState", state, 1)
    python = ImuDeadReckoner(nav_parameters)
    python.initNavState(**state)
    rng = np.random.default_rng(7)

    for k in range(1, 11):
        reading = messaging.IMUSensorMsgPayload()
        reading.AngVelPlatform = (0.02 * rng.normal(size=3)).tolist()
        reading.AccelPlatform = (1e-3 * rng.normal(size=3)).tolist()
        adapter.tick(k * NS, {"imu": reading})
        python.step(
            t=float(k),
            imu=Gnc.ImuReading(np.array(reading.AngVelPlatform), np.array(reading.AccelPlatform)),
        )

    latest = _latest(decoded(station))
    np.testing.assert_allclose(latest["nav.bodyEciAttitude"], python.q_BN, rtol=0, atol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciPos"], python.r_BN_N, rtol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciVel"], python.v_BN_N, rtol=1e-12)


FLIGHT = """
from harness.mission import Mission, mission_tests

globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="ImuDeadReckoning", build="fprime", scenarios=("TST001",)
        )
    )
)
"""
"""The F´ build flown through the repository's leo500 scenario, TST001."""


def _contents(path: Path) -> dict[str, object]:
    """Every dataset of a run file, and every root attribute but its creation time.

    Args:
        path: the run file.

    Returns:
        Each dataset's values and attributes by its path, and each root attribute by `@<name>`.
    """
    contents: dict[str, object] = {}

    def visit(name: str, node: object) -> None:
        """Keep a dataset's values and attributes.

        Args:
            name: the node's path in the file.
            node: the group or dataset.
        """
        if isinstance(node, h5py.Dataset):
            contents[name] = (node[()], dict(node.attrs))

    with h5py.File(path, "r") as f:
        f.visititems(visit)
        contents |= {f"@{k}": v for k, v in f.attrs.items() if k != "created_utc"}
    return contents


def test_a_case_flown_after_another_writes_the_run_file_it_writes_alone(
    pytester: pytest.Pytester,
):
    """Case 1 flown alone and after case 0 in one process gives the same run file, every row.

    The rate group's health datasets are compared with nav's: its `CycleCount` and the channels it
    writes only on change are what a deployment kept across cases would carry over. It also holds
    the rate group's health to F´'s stub clock, under nav's real load: its cycle times read 0, where
    a wall clock would make them differ between the two runs. Case 0's run file differs from case
    1's, so a comparison that cannot tell cases apart would show.

    Args:
        pytester: the project the flights run in, each run in one process of its own, xdist off.
    """
    pytester.makepyfile(test_flights=FLIGHT)
    test = "test_flights.py::Test_imu_spacecraft::test_ImuDeadReckoning_fprime_leo500"

    options = ("-p", "no:cacheprovider", "-p", "no:xdist")

    pytester.runpytest_subprocess(*options, f"{test}[1]").assert_outcomes(passed=1)
    [alone] = pytester.path.rglob("run_0001.h5")
    alone = shutil.move(alone, pytester.path / "alone.h5")
    pytester.runpytest_subprocess(*options, f"{test}[0]", f"{test}[1]").assert_outcomes(passed=2)
    [first] = pytester.path.rglob("run_0000.h5")
    [after] = pytester.path.rglob("run_0001.h5")

    alone, after, first = _contents(alone), _contents(after), _contents(first)
    assert any(name.startswith("tlm/nav.") for name in alone)
    assert any(name.startswith("tlm/navRateGroup.") for name in alone)
    assert not alone["tlm/navRateGroup.CycleTime"][0].any()
    assert sorted(alone) == sorted(after)
    for name, value in alone.items():
        np.testing.assert_equal(after[name], value, err_msg=name)
    with pytest.raises(AssertionError):
        np.testing.assert_equal(first, alone)
