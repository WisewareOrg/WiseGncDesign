"""The deployment's pins through the ground station: commands up, responses and telemetry down.

Skipped without the deployment `just fsw` builds.
"""

import numpy as np
import pytest

from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY, extension

pytest.importorskip("lab._wise_fsw", reason="the F´ build is absent; run `just fsw`")
_wise_fsw = extension()

STATION = FprimeStation(_wise_fsw, Dictionary(DICTIONARY))
"""The ground station on the deployment, with the dictionary the build generated."""

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
    """Drains the telemetry writes, as values.

    Returns:
        Each write's channel name, F´ time tag in ns and value, oldest first.
    """
    return [(name, t, STATION.values(name, [raw])[0]) for name, t, raw in STATION.telemetry()]


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


def test_every_write_comes_down_once_in_order_with_its_f_prime_time():
    """The writes of two ticks come down in the order written, each tagged with its tick's time.

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


def test_boot_leaves_nothing_of_the_previous_case():
    """A case that ends with a command queued and GroundLink undrained leaves nothing to the next.

    The queued command runs at boot, before nav is configured idle, and GroundLink is cleared after.
    """
    _boot()
    STATION.uplink("nav.initNavState", STATE, 1)
    _step(NS)
    STATION.uplink("nav.initNavState", STATE, 2)

    _boot()
    _step(NS)

    assert _writes() == [("nav.navState", NS, "idle")]
    assert _responses() == []


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
