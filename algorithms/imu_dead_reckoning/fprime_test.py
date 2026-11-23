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
from fsw.codegen.deployment import bus_port, configuration_model
from fsw.codegen.fpp_types import Gnc
from ground.fprime_station import FprimeStation
from lab.bus_emulator import serialize

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


CONFIGURATION = "ImuDeadReckoning"
"""The dead reckoner's configuration, the only one this module's cases fly."""

NAV_INSTANCE = f"{CONFIGURATION}.nav"
"""Nav's qualified instance name, which the record keys its parameters by."""


@pytest.fixture(scope="module")
def imu_bus() -> Callable[[Any, Any], list[tuple[int, bytes]]]:
    """One IMU reading's bus for a step: the IMU role's message bytes on its LabBusDriver port.

    The port is the one the configuration's deployment wires to the IMU role's CDH input, `imuIn`.

    Returns:
        A function of the angular velocity and the acceleration, each three values in the
        platform frame, giving `[(port, bytes)]`, the message's dv and dr zero.
    """
    port = bus_port(CONFIGURATION, "imuIn")

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
    boot: Callable[..., tuple[ModuleType, FprimeStation]],
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Booted and ticked for one run of nav, nav writes `navState` idle, once, and nothing else.

    That a rate group runs its members once every divider ticks is `lab/link_test.py`'s
    `test_each_rate_group_runs_once_every_divider_ticks`.

    Args:
        boot: boots the configuration on the parameters given.
        decoded: drains the station's telemetry as values.
        imu_bus: the IMU message's bus for a reading.
    """
    fsw, station = boot(CONFIGURATION, {NAV_INSTANCE: NAV})
    divider = int(configuration_model(CONFIGURATION).constants[f"{CONFIGURATION}.navDivider"])
    for tick in range(1, divider + 1):
        fsw.step(t_ns=tick * NS, bus=imu_bus(np.zeros(3), np.zeros(3)))

    assert [(n, v) for n, _, v in decoded(station) if n.startswith("nav.")] == [("nav.navState", "idle")]


def test_initialization_writes_the_initial_quaternion_with_w_nonnegative(
    boot: Callable[..., tuple[ModuleType, FprimeStation]],
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    imu_bus: Callable[[Any, Any], list[tuple[int, bytes]]],
):
    """Commanded -q as of t = 0 and stepped 1 s at zero rate, the deployment writes q.

    Args:
        boot: boots the configuration on the parameters given.
        decoded: drains the station's telemetry as values.
        imu_bus: the IMU message's bus for a reading.
    """
    fsw, station = boot(CONFIGURATION, {NAV_INSTANCE: NAV})
    station.uplink("nav.initNavState", _state(0.0, -Q0), 1)
    fsw.step(t_ns=NS, bus=imu_bus(np.zeros(3), np.zeros(3)))

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
    boot: Callable[..., tuple[ModuleType, FprimeStation]],
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
        boot: boots the configuration on the parameters given.
        decoded: drains the station's telemetry as values.
        rate_rad_s: rad/s, the gyro reading's magnitude.
        step_ns: ns between readings.
        epoch_s: s, the epoch of the commanded state.
        count: the readings after the epoch.
        seed: the readings' random seed.
        nav_parameters: nav's parameters, which the case's record holds.
        imu_bus: the IMU message's bus for a reading.
    """
    fsw, station = boot(CONFIGURATION, {NAV_INSTANCE: nav_parameters})
    rng = np.random.default_rng(seed)
    readings = [(rate_rad_s * rng.normal(size=3), 1e-3 * rng.normal(size=3)) for _ in range(count)]
    python = ImuDeadReckoner(nav_parameters)
    python.initNavState(**_state(float(epoch_s)))
    before = epoch_s * NS // step_ns
    for k in range(1, before + 1):
        fsw.step(t_ns=k * step_ns, bus=imu_bus(np.zeros(3), np.zeros(3)))
    station.uplink("nav.initNavState", _state(float(epoch_s)), 1)

    for k, (omega, accel) in enumerate(readings, start=before + 1):
        python.step(t=k * step_ns / NS, imu=Gnc.ImuReading(omega, accel))
        fsw.step(t_ns=k * step_ns, bus=imu_bus(omega, accel))

    assert station.responses() == [(1, "OK", None)]
    _assert_matches(_latest(decoded(station)), python)
