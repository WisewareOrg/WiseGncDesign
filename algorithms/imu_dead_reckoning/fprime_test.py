"""The F´ build of the dead reckoner against the notebook's, reading for reading.

Skipped without the deployment `just fsw` builds.
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from Basilisk.architecture import messaging
from scipy.spatial.transform import Rotation

from algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from fsw.codegen.deployment import bus_port, contract_files
from fsw.codegen.fpp_model import read
from fsw.codegen.fpp_types import Gnc
from fsw.codegen.roles import roles
from ground.fprime_station import FprimeStation
from lab import built
from lab.bus_emulator import serialize

if not built("ImuDeadReckoning"):
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


def _state(epoch: float, attitude: np.ndarray = Q0) -> dict[str, Any]:
    """`initNavState`'s arguments: the state as of `epoch`, at `R0` and `V0`.

    Args:
        epoch: s, the FSW time the state applies at.
        attitude: body to ECI, W X Y Z.

    Returns:
        The arguments by parameter name.
    """
    return {"epoch": epoch, "attitude": attitude, "position": R0, "velocity": V0}


def test_a_booted_reckoner_reports_idle_and_no_state(
    booted: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Booted and ticked once, nav writes `navState` idle, once, and nothing else.

    `navDivider` is 1, so the tick is one run of nav, and its one write is `navState`.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        imu_bus: the IMU message's bus for a reading.
    """
    booted.step(t_ns=NS, bus=imu_bus(np.zeros(3), np.zeros(3)))

    assert [(n, v) for n, _, v in decoded(station) if n.startswith("nav.")] == [
        ("nav.navState", "idle")
    ]


@pytest.mark.parametrize("sign", [1.0, -1.0], ids=["w-positive", "w-negative"])
def test_initialization_writes_the_initial_quaternion_with_w_nonnegative(
    booted: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    sign: float,
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Commanded q or -q as of t = 0 and stepped 1 s at zero rate, the deployment writes q.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        sign: the sign the initial quaternion is given with.
        imu_bus: the IMU message's bus for a reading.
    """
    station.uplink("nav.initNavState", _state(0.0, sign * Q0), 1)
    booted.step(t_ns=NS, bus=imu_bus(np.zeros(3), np.zeros(3)))

    attitude = _latest(decoded(station))["nav.bodyEciAttitude"]
    np.testing.assert_allclose(attitude, Q0, rtol=0, atol=1e-15)


@pytest.mark.parametrize(
    ("rate_rad_s", "step_ns", "epoch_s", "count", "seed", "nav_parameters"),
    [
        (0.02, NS, 0, 600, 7, NAV),
        (0.5, NS, 0, 600, 7, NAV),
        (0.02, NS // 10, 0, 600, 7, NAV),
        (0.02, NS, 60, 300, 5, NAV),
        (0.02, NS, 0, 60, 13, NAV._replace(mu=4.9048695e12)),
    ],
    ids=["slow", "past-a-half-turn", "at-10-Hz", "from-60-s", "moon-mu"],
)
def test_the_fprime_build_matches_the_notebook_reading_for_reading(
    booted: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    rate_rad_s: float,
    step_ns: int,
    epoch_s: int,
    count: int,
    seed: int,
    nav_parameters: Gnc.ImuDeadReckonerParameters,
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Commanded a state as of its epoch and fed the same readings, the builds agree to rounding.

    Before the epoch the deployment steps on zero readings; the command runs at the first step
    after it, which propagates from the epoch. The faster rate turns the body past 180 degrees, so
    W changes sign and both flip q; the 10 Hz case ticks between whole seconds. Booted on a record
    with the Moon's mu, nav propagates as the notebook does on that mu; Earth's differs by a factor
    of 81, so a nav flying any other mu than the record's fails.

    Args:
        booted: the test's copy of the deployment, booted on the case's parameters.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        rate_rad_s: rad/s, the gyro reading's magnitude.
        step_ns: ns between readings.
        epoch_s: s, the epoch of the commanded state.
        count: the readings after the epoch.
        seed: the readings' random seed.
        nav_parameters: nav's parameters, which the case's record holds.
        imu_bus: the IMU message's bus for a reading.
    """
    rng = np.random.default_rng(seed)
    readings = [(rate_rad_s * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(count)]
    python = ImuDeadReckoner(nav_parameters)
    python.initNavState(**_state(float(epoch_s)))
    before = epoch_s * NS // step_ns
    for k in range(1, before + 1):
        booted.step(t_ns=k * step_ns, bus=imu_bus(np.zeros(3), np.zeros(3)))
    station.uplink("nav.initNavState", _state(float(epoch_s)), 1)

    for k, (omega, accel) in enumerate(readings, start=before + 1):
        python.step(t=k * step_ns / NS, imu=Gnc.ImuReading(omega, accel))
        booted.step(t_ns=k * step_ns, bus=imu_bus(omega, accel))

    assert station.responses() == [(1, "OK", None)]
    _assert_matches(_latest(decoded(station)), python)
