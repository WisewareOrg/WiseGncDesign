"""The deployment's pins through the ground station: commands up, responses and telemetry down.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
import math
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import read
from ground.fprime_station import FprimeStation

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

NS = 1_000_000_000
"""ns per s."""

GNC = Path(__file__).resolve().parents[1] / "fsw" / "fpp" / "gnc"
"""The GNC sub-topologies."""

STATE = {
    "epoch": 0.0,
    "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
    "position": np.array([6871.0e3, 0.0, 0.0]),
    "velocity": np.array([0.0, 5.4e3, 5.4e3]),
}
"""`nav.initNavState`'s arguments: a state at t = 0."""


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
    parameter_ids: list[int],
):
    """An uplinked command waits for the next step, then answers `OK` under the ground's context.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    fsw.boot(prm, parameter_ids)

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
    parameter_ids: list[int],
):
    """Nav's writes of two ticks come down in the order written, each tagged with its tick's time.

    The command's handler writes `navState` alone, before the step writes the estimate.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    fsw.boot(prm, parameter_ids)
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
    parameter_ids: list[int],
):
    """A tick at 1.500007 s tags its write with that time in ns, microseconds included.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    fsw.boot(prm, parameter_ids)
    t_ns = NS + 500_000_000 + 7_000

    _step(fsw, t_ns)

    assert _writes(station) == [("nav.navState", t_ns, "idle")]


def test_the_rate_group_s_health_repeats_on_the_stub_clock(
    fsw: ModuleType, station: FprimeStation, prm: str, parameter_ids: list[int]
):
    """With nav propagating, every cycle time the rate group writes is 0, on F´'s stub clock.

    On the wall clock some cycles take a microsecond or more, so a cycle time that is not 0 shows a
    deployment without the stub; on a much faster host it could still read 0. The cycle count is
    held to one more per tick.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    ticks = 500
    fsw.boot(prm, parameter_ids)
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


def test_each_rate_group_runs_once_every_divider_ticks(
    fsw: ModuleType, station: FprimeStation, prm: str, parameter_ids: list[int]
):
    """Each rate group's `CycleCount` advances by one once every divider ticks, its own divider.

    A rate group `<stem>RateGroup` runs at the constant `<stem>Divider` of its module in the GNC
    sub-topologies. The count is taken over ten of the dividers' least common multiple, a whole
    number of every divider, which holds whatever tick the driver starts on.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    constants = read((*contract_files(), *sorted(GNC.glob("*.fpp")))).constants
    dividers = {
        name.rsplit(".", 1)[1].removesuffix("Divider") + "RateGroup": divider
        for name, divider in constants.items()
        if name.endswith("Divider")
    }
    assert dividers
    ticks = 10 * math.lcm(*dividers.values())
    fsw.boot(prm, parameter_ids)
    station.telemetry()

    for tick in range(1, ticks + 1):
        _step(fsw, tick * NS)

    writes = station.telemetry()
    for group, divider in dividers.items():
        name = f"{group}.CycleCount"
        counts = station.values(name, [raw for written, _, raw in writes if written == name])
        assert len(counts) == ticks // divider, group
        assert np.diff(counts).tolist() == [1] * (len(counts) - 1), group


def test_the_pump_raises_naming_a_queue_its_bound_leaves_holding_messages(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
    parameter_ids: list[int],
):
    """A queue still holding messages after the pump's rounds raises, naming it, never hangs.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    fsw.boot(prm, parameter_ids)
    station.uplink("cmdDisp.CMD_NO_OP", {}, 3)

    with pytest.raises(
        RuntimeError, match=r"queue WiseFsw\.cmdDisp did not drain: messages left 1, rounds 1$"
    ):
        fsw.pump(rounds=1)
    fsw.pump()

    assert _responses(station) == [(3, "OK")]
