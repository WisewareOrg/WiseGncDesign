"""The deployment's pins through the ground station: commands up, responses and telemetry down.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from fsw.codegen.fpp_types import Gnc
from ground import parameters
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY
from lab.power_cycle import power_cycle

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

WISE_FSW = Dictionary(DICTIONARY)
"""The deployment's dictionary, which the build generated."""

MU = 3.986004360e14
"""m^3/s^2, Earth's gravitational parameter, as the scenarios set it."""

NS = 1_000_000_000
"""ns per s."""

STATE = {
    "epoch": 0.0,
    "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
    "position": np.array([6871.0e3, 0.0, 0.0]),
    "velocity": np.array([0.0, 5.4e3, 5.4e3]),
}
"""`nav.initNavState`'s arguments: a state at t = 0."""


@pytest.fixture
def fsw() -> ModuleType:
    """A fresh copy of the deployment, not yet booted.

    Returns:
        The copy.
    """
    return power_cycle()


@pytest.fixture
def prm(tmp_path: Path) -> str:
    """A case's parameter file: Earth's mu, the IMU mounted at identity.

    Args:
        tmp_path: the case's directory.

    Returns:
        The `.dat`'s path.
    """
    nav = Gnc.ImuDeadReckonerParameters(mu=MU, dcm_PB=np.eye(3))
    record = parameters.write(nav, tmp_path / "run_0000.prm.json")
    return str(parameters.dat(record, DICTIONARY))


@pytest.fixture
def station(fsw: ModuleType) -> FprimeStation:
    """The ground station on the test's copy.

    Args:
        fsw: the test's copy.

    Returns:
        The station.
    """
    return FprimeStation(fsw, WISE_FSW)


def _boot(fsw: ModuleType, prm: str) -> None:
    """Boots a copy idle, mounted at identity.

    Args:
        fsw: the copy.
        prm: the case's parameter file.
    """
    fsw.boot(prm, sorted(WISE_FSW.parameters_by_id))


def _step(fsw: ModuleType, t_ns: int) -> None:
    """Steps a copy to `t_ns` on a zero IMU reading.

    Args:
        fsw: the copy.
        t_ns: ns, the tick's time.
    """
    fsw.step(t_ns=t_ns, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))


def _writes(station: FprimeStation) -> list[tuple[str, int, object]]:
    """Drains the telemetry writes and keeps nav's, as values.

    Args:
        station: the station on the copy.

    Returns:
        Each of nav's writes' channel name, F´ time tag in ns and value, oldest first.
    """
    writes = station.telemetry()
    return [
        (name, t, station.values(name, [raw])[0])
        for name, t, raw in writes
        if name.startswith("nav.")
    ]


def _responses(station: FprimeStation) -> list[tuple[int, str]]:
    """Drains the command responses, named.

    Args:
        station: the station on the copy.

    Returns:
        Each response's context and `Fw.CmdResponse` constant name, oldest first.
    """
    return [(context, response) for context, response, _ in station.responses()]


def test_a_command_runs_at_the_next_step_and_is_answered_ok_under_its_context(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
):
    """An uplinked command waits for the next step, then answers `OK` under the ground's context.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
    """
    _boot(fsw, prm)

    station.uplink("nav.initNavState", STATE, 42)
    assert _responses(station) == []
    _step(fsw, NS)

    assert _responses(station) == [(42, "OK")]


def test_a_packet_larger_than_f_prime_s_buffer_is_refused_naming_its_size(fsw: ModuleType):
    """`uplink` refuses a packet too large for the command buffer, before the dispatcher sees it.

    Args:
        fsw: the test's copy of the deployment.
    """
    with pytest.raises(ValueError, match="packet of 10000 bytes exceeds"):
        fsw.uplink(bytes(10_000), 1)


def test_nav_s_writes_come_down_once_in_order_with_their_f_prime_time(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
):
    """Nav's writes of two ticks come down in the order written, each tagged with its tick's time.

    The command's handler writes `navState` alone, before the step writes the estimate.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
    """
    _boot(fsw, prm)
    station.uplink("nav.initNavState", STATE, 1)
    _step(fsw, NS)
    _step(fsw, 2 * NS)

    writes = _writes(station)

    estimate = ["nav.navState", "nav.bodyEciPos", "nav.bodyEciVel", "nav.bodyEciAttitude"]
    assert [(name, t) for name, t, _ in writes] == [
        ("nav.navState", NS),
        *[(name, NS) for name in estimate],
        *[(name, 2 * NS) for name in estimate],
    ]
    assert [value for name, _, value in writes if name == "nav.navState"] == [
        "initialized",
        "propagated",
        "propagated",
    ]
    assert _writes(station) == []


def test_a_write_between_whole_seconds_is_tagged_to_the_microsecond(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
):
    """A tick at 1.500007 s tags its write with that time in ns, microseconds included.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
    """
    _boot(fsw, prm)
    t_ns = NS + 500_000_000 + 7_000

    _step(fsw, t_ns)

    assert _writes(station) == [("nav.navState", t_ns, "idle")]


def test_the_rate_group_s_health_repeats_on_the_stub_clock(
    fsw: ModuleType, station: FprimeStation, prm: str
):
    """With nav propagating, every cycle time the rate group writes is 0, on F´'s stub clock.

    On the wall clock some cycles take a microsecond or more, so a cycle time that is not 0 shows a
    deployment without the stub; on a much faster host it could still read 0. The cycle count is
    held to one more per tick.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
    """
    ticks = 500
    _boot(fsw, prm)
    station.uplink("nav.initNavState", STATE, 1)
    station.telemetry()

    for tick in range(1, ticks + 1):
        fsw.step(
            t_ns=tick * NS,
            angVelPlatform=np.array([0.01, -0.02, 0.03]),
            accelPlatform=np.array([0.1, 0.2, -0.3]),
        )

    writes = station.telemetry()

    def values(channel: str) -> np.ndarray:
        """The values the rate group wrote to one channel.

        Args:
            channel: the channel's name within `navRateGroup`.

        Returns:
            Its values, oldest first.
        """
        name = f"navRateGroup.{channel}"
        return station.values(name, [raw for written, _, raw in writes if written == name])

    assert values("CycleTime").tolist() == [0] * ticks
    assert not values("MaxCycleTime").any()
    assert np.diff(values("CycleCount")).tolist() == [1] * (ticks - 1)
    assert len(values("CycleCount")) == ticks


def test_the_pump_raises_naming_a_queue_its_bound_leaves_holding_messages(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
):
    """A queue still holding messages after the pump's rounds raises, naming it, never hangs.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
    """
    _boot(fsw, prm)
    station.uplink("cmdDisp.CMD_NO_OP", {}, 3)

    with pytest.raises(
        RuntimeError, match=r"queue WiseFsw\.cmdDisp did not drain: messages left 1, rounds 1$"
    ):
        fsw.pump(rounds=1)
    fsw.pump()

    assert _responses(station) == [(3, "OK")]
