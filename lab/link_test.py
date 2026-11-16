"""The deployment's pins through the ground station: commands up, responses and telemetry down.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
import math
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from fsw.codegen.deployment import configurations, fpp_files
from fsw.codegen.fpp_model import read
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation

if not all(importlib.util.find_spec(f"lab._wise_fsw_{c}") for c in configurations()):
    pytest.skip("an F´ build is absent; run `just fsw`", allow_module_level=True)

NS = 1_000_000_000
"""ns per s."""

STATE = {
    "epoch": 0.0,
    "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
    "position": np.array([6871.0e3, 0.0, 0.0]),
    "velocity": np.array([0.0, 5.4e3, 5.4e3]),
}
"""`nav.initNavState`'s arguments: a state at t = 0."""


def _nav(writes: list[tuple[str, int, Any]]) -> list[tuple[str, int, Any]]:
    """Nav's writes among drained ones.

    Args:
        writes: drained writes, as `decoded` gives them.

    Returns:
        Those of nav's channels, in order.
    """
    return [write for write in writes if write[0].startswith("nav.")]


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
    bus: list[tuple[int, bytes]],
):
    """An uplinked command waits for the next step, then answers `OK` under the ground's context.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    fsw.boot(prm, parameter_ids)

    station.uplink("nav.initNavState", STATE, 42)
    assert _responses(station) == []
    fsw.step(t_ns=NS, bus=bus)

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
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """Nav's writes of two ticks come down in the order written, each tagged with its tick's time.

    The command's handler writes `navState` alone, before the step writes the estimate.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    fsw.boot(prm, parameter_ids)
    station.uplink("nav.initNavState", STATE, 1)
    fsw.step(t_ns=NS, bus=bus)
    fsw.step(t_ns=2 * NS, bus=bus)

    writes = _nav(decoded(station))

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
    assert _nav(decoded(station)) == []


def test_a_write_between_whole_seconds_is_tagged_to_the_microsecond(
    fsw: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """A tick at 1.500007 s tags its write with that time in ns, microseconds included.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        decoded: drains the station's telemetry as values.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    fsw.boot(prm, parameter_ids)
    t_ns = NS + 500_000_000 + 7_000

    fsw.step(t_ns=t_ns, bus=bus)

    assert _nav(decoded(station)) == [("nav.navState", t_ns, "idle")]


def test_the_rate_group_s_health_repeats_on_the_stub_clock(
    fsw: ModuleType,
    station: FprimeStation,
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """With nav propagating, every cycle time the rate group writes is 0, on F´'s stub clock.

    On the wall clock some cycles take a microsecond or more, so a cycle time that is not 0 shows a
    deployment without the stub; on a much faster host it could still read 0. How often the rate
    group runs is `test_each_rate_group_runs_once_every_divider_ticks`'s.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    ticks = 500
    fsw.boot(prm, parameter_ids)
    station.uplink("nav.initNavState", STATE, 1)
    station.telemetry()

    for tick in range(1, ticks + 1):
        fsw.step(t_ns=tick * NS, bus=bus)

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

    cycle_times = values("CycleTime")
    assert cycle_times.size
    assert not cycle_times.any()
    assert not values("MaxCycleTime").any()


def test_each_rate_group_runs_once_every_divider_ticks(
    fsw: ModuleType,
    station: FprimeStation,
    dictionary: Dictionary,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """Each rate group's `CycleCount` advances by one once every divider ticks, its own divider.

    The deployment's configuration is the module of its algorithm instances, a GNC sub-topology
    named for its file. A rate group `<stem>RateGroup` runs at the constant `<stem>Divider` of that
    module. The count is taken over ten of the dividers' least common multiple, a whole number of
    every divider, which holds whatever tick the driver starts on.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        dictionary: its dictionary.
        tmp_path: where the configuration's topology is rendered.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    instances = dictionary.algorithm_instances()
    (configuration,) = {i.name.split(".", 1)[0] for i in instances}
    constants = read(fpp_files(configuration, tmp_path)).constants
    dividers = {
        name.removeprefix(f"{configuration}.").removesuffix("Divider") + "RateGroup": divider
        for name, divider in constants.items()
        if name.startswith(f"{configuration}.") and name.endswith("Divider")
    }
    assert dividers
    ticks = 10 * math.lcm(*dividers.values())
    fsw.boot(prm, parameter_ids)
    station.telemetry()

    for tick in range(1, ticks + 1):
        fsw.step(t_ns=tick * NS, bus=bus)

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
