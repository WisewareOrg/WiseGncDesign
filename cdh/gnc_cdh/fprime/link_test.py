"""The deployment's link, driven through the binding: commands up, responses and telemetry down.

Skipped without the deployment `just fsw` builds.
"""

import json

import numpy as np
import pytest

from gnc_cdh.dictionary import DecodeError, Dictionary
from gnc_cdh.fprime import DICTIONARY, extension

pytest.importorskip("gnc_cdh.fprime._wise_fsw", reason="the F´ build is absent; run `just fsw`")
_wise_fsw = extension()

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

INIT = WISE_FSW.encode_command("nav.initNavState", STATE)
"""`nav.initNavState` with `STATE`, as F´ serializes it."""

HEAD = INIT[:6]
"""`INIT`'s descriptor and opcode."""

UNKNOWN = max(c["opcode"] for c in json.loads(DICTIONARY.read_text())["commands"]) + 1
"""An opcode no instance of the deployment has."""


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
    """Drains the telemetry writes, decoded.

    Returns:
        Each write's channel name, F´ time tag in ns and value, oldest first.
    """
    channels = WISE_FSW.channels_by_id
    return [(channels[i].name, t, channels[i].decode(raw)) for i, t, raw in _wise_fsw.telemetry()]


def _responses() -> list[tuple[int, str]]:
    """Drains the command responses, named.

    Returns:
        Each response's context and `Fw.CmdResponse` constant name, oldest first.
    """
    names = {value: name for name, value in WISE_FSW.responses.items()}
    return [(context, names[value]) for context, value in _wise_fsw.responses()]


def test_a_command_runs_at_the_next_step_and_is_answered_ok_under_its_context():
    """An uplinked command waits for the next step, then answers `OK` under the ground's context."""
    _boot()

    _wise_fsw.uplink(INIT, 42)
    assert _responses() == []
    _step(NS)

    assert _responses() == [(42, "OK")]


@pytest.mark.parametrize(
    ("packet", "response"),
    [
        (INIT[:2] + UNKNOWN.to_bytes(4, "big") + INIT[6:], "INVALID_OPCODE"),
        (b"\x00\x01" + INIT[2:], "VALIDATION_ERROR"),
        (INIT[:4], "VALIDATION_ERROR"),
        (INIT[:-8], "FORMAT_ERROR"),
        (HEAD, "FORMAT_ERROR"),
        (INIT + bytes(8), "FORMAT_ERROR"),
    ],
    ids=[
        "unknown-opcode",
        "not-a-command",
        "truncated-head",
        "short-arguments",
        "no-arguments",
        "extra",
    ],
)
def test_a_rejected_packet_gets_f_prime_s_response_and_the_dictionary_s_and_nav_stays_idle(
    packet: bytes, response: str
):
    """F´ answers a bad packet with the response the dictionary's decode gives it, and runs nothing.

    Args:
        packet: the bad packet.
        response: the `Fw.CmdResponse` both give it.
    """
    _boot()
    with pytest.raises(DecodeError) as decoded:
        WISE_FSW.decode_command(packet, "nav")

    _wise_fsw.uplink(packet, 7)
    _step(NS)

    assert decoded.value.response == response
    assert _responses() == [(7, response)]
    assert _writes() == [("nav.navState", NS, "idle")]


def test_a_packet_larger_than_f_prime_s_buffer_is_refused_naming_its_size():
    """`uplink` refuses a packet too large for the command buffer, before the dispatcher sees it."""
    with pytest.raises(ValueError, match="packet of 10000 bytes exceeds"):
        _wise_fsw.uplink(bytes(10_000), 1)


def test_every_write_comes_down_once_in_order_with_its_f_prime_time():
    """The writes of two ticks come down in the order written, each tagged with its tick's time.

    The command's handler writes `navState` alone, before the step writes the estimate.
    """
    _boot()
    _wise_fsw.uplink(INIT, 1)
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


def test_boot_leaves_nothing_of_the_previous_case():
    """A case that ends with a command queued and its link undrained leaves nothing to the next.

    The queued command runs at boot, before nav is configured idle, and the link is cleared after.
    """
    _boot()
    _wise_fsw.uplink(INIT, 1)
    _step(NS)
    _wise_fsw.uplink(INIT, 2)

    _boot()
    _step(NS)

    assert _writes() == [("nav.navState", NS, "idle")]
    assert _responses() == []


def test_the_pump_raises_naming_a_queue_its_bound_leaves_holding_messages():
    """A queue still holding messages after the pump's rounds raises, naming it, never hangs."""
    _boot()
    _wise_fsw.uplink(WISE_FSW.encode_command("cmdDisp.CMD_NO_OP", {}), 3)

    with pytest.raises(
        RuntimeError, match=r"queue WiseFsw\.cmdDisp still holds 1 messages after 1"
    ):
        _wise_fsw.pump(rounds=1)
    _wise_fsw.pump()

    assert _responses() == [(3, "OK")]
