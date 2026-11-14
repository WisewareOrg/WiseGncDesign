"""The deployment's pins through the ground station: commands up, responses and telemetry down.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
from types import ModuleType

import numpy as np
import pytest

from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY
from lab.power_cycle import power_cycle

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

WISE_FSW = Dictionary(DICTIONARY)
"""The deployment's dictionary, which the build generated."""

_wise_fsw: ModuleType
"""The test's fresh copy of the deployment."""

STATION: FprimeStation
"""The ground station on the test's copy."""


@pytest.fixture(autouse=True)
def _fresh_copy() -> None:
    """Power-cycles the deployment for each test, with a station on the fresh copy."""
    global _wise_fsw, STATION
    _wise_fsw = power_cycle()
    STATION = FprimeStation(_wise_fsw, WISE_FSW)


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


def _boot() -> None:
    """Boots the deployment idle, mounted at identity."""
    _wise_fsw.boot(mu=MU, dcm_PB=np.eye(3))


def _step(t_ns: int) -> None:
    """Steps the deployment to `t_ns` on a zero IMU reading.

    Args:
        t_ns: ns, the tick's time.
    """
    _wise_fsw.step(t_ns=t_ns, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))


def _writes() -> list[tuple[str, int, object]]:
    """Drains the telemetry writes and keeps nav's, as values.

    Returns:
        Each of nav's writes' channel name, F´ time tag in ns and value, oldest first.
    """
    writes = STATION.telemetry()
    return [
        (name, t, STATION.values(name, [raw])[0])
        for name, t, raw in writes
        if name.startswith("nav.")
    ]


def _responses() -> list[tuple[int, str]]:
    """Drains the command responses, named.

    Returns:
        Each response's context and `Fw.CmdResponse` constant name, oldest first.
    """
    return [(context, response) for context, response, _ in STATION.responses()]


def test_a_command_runs_at_the_next_step_and_is_answered_ok_under_its_context():
    """An uplinked command waits for the next step, then answers `OK` under the ground's context."""
    _boot()

    STATION.uplink("nav.initNavState", STATE, 42)
    assert _responses() == []
    _step(NS)

    assert _responses() == [(42, "OK")]


def test_a_packet_larger_than_f_prime_s_buffer_is_refused_naming_its_size():
    """`uplink` refuses a packet too large for the command buffer, before the dispatcher sees it."""
    with pytest.raises(ValueError, match="packet of 10000 bytes exceeds"):
        _wise_fsw.uplink(bytes(10_000), 1)


def test_nav_s_writes_come_down_once_in_order_with_their_f_prime_time():
    """Nav's writes of two ticks come down in the order written, each tagged with its tick's time.

    The command's handler writes `navState` alone, before the step writes the estimate.
    """
    _boot()
    STATION.uplink("nav.initNavState", STATE, 1)
    _step(NS)
    _step(2 * NS)

    writes = _writes()

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
    assert _writes() == []


def test_a_write_between_whole_seconds_is_tagged_to_the_microsecond():
    """A tick at 1.500007 s tags its write with that time in ns, microseconds included."""
    _boot()
    t_ns = NS + 500_000_000 + 7_000

    _step(t_ns)

    assert _writes() == [("nav.navState", t_ns, "idle")]


def test_the_rate_group_s_health_repeats_on_the_stub_clock():
    """With nav propagating, every cycle time the rate group writes is 0, on F´'s stub clock.

    On the wall clock some cycles take a microsecond or more, so a cycle time that is not 0 shows a
    deployment without the stub; on a much faster host it could still read 0. The cycle count is
    held to one more per tick.
    """
    ticks = 500
    _boot()
    STATION.uplink("nav.initNavState", STATE, 1)
    STATION.telemetry()

    for tick in range(1, ticks + 1):
        _wise_fsw.step(
            t_ns=tick * NS,
            angVelPlatform=np.array([0.01, -0.02, 0.03]),
            accelPlatform=np.array([0.1, 0.2, -0.3]),
        )

    writes = STATION.telemetry()

    def values(channel: str) -> np.ndarray:
        """The values the rate group wrote to one channel.

        Args:
            channel: the channel's name within `navRateGroup`.

        Returns:
            Its values, oldest first.
        """
        name = f"navRateGroup.{channel}"
        return STATION.values(name, [raw for written, _, raw in writes if written == name])

    assert values("CycleTime").tolist() == [0] * ticks
    assert not values("MaxCycleTime").any()
    assert np.diff(values("CycleCount")).tolist() == [1] * (ticks - 1)
    assert len(values("CycleCount")) == ticks


def test_the_pump_raises_naming_a_queue_its_bound_leaves_holding_messages():
    """A queue still holding messages after the pump's rounds raises, naming it, never hangs."""
    _boot()
    STATION.uplink("cmdDisp.CMD_NO_OP", {}, 3)

    with pytest.raises(
        RuntimeError, match=r"queue WiseFsw\.cmdDisp did not drain: messages left 1, rounds 1$"
    ):
        _wise_fsw.pump(rounds=1)
    _wise_fsw.pump()

    assert _responses() == [(3, "OK")]
