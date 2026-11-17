"""The deployment's pins through the ground station: commands up, responses and telemetry down.

The command is F´'s own `cmdDisp.CMD_NO_OP`, and the writes are each `Svc.PassiveRateGroup`'s
health channels, which every deployment has. Skipped without the deployment `just fsw` builds.
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
from ground.fprime_station import FprimeStation

if not all(importlib.util.find_spec(f"lab._wise_fsw_{c}") for c in configurations()):
    pytest.skip("an F´ build is absent; run `just fsw`", allow_module_level=True)

NS = 1_000_000_000
"""ns per s."""


def _health(
    writes: list[tuple[str, int, Any]], rate_groups: list[str]
) -> list[tuple[str, int, Any]]:
    """The rate groups' writes among drained ones.

    Args:
        writes: drained writes, as `decoded` gives them.
        rate_groups: the rate groups.

    Returns:
        Those of the rate groups' channels, in order.
    """
    return [write for write in writes if write[0].startswith(tuple(f"{g}." for g in rate_groups))]


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

    station.uplink("cmdDisp.CMD_NO_OP", {}, 42)
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


def test_the_rate_groups_writes_come_down_once_in_order_with_their_f_prime_time(
    fsw: ModuleType,
    station: FprimeStation,
    rate_groups: list[str],
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """Each rate group's writes of two ticks come down in the order written, tagged with each tick.

    Every write of the first tick comes before every write of the second, and each rate group's
    `CycleCount` counts up from 1 by one per run, at whatever divider it runs.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        rate_groups: the copy's rate groups.
        decoded: drains the station's telemetry as values.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    fsw.boot(prm, parameter_ids)
    fsw.step(t_ns=NS, bus=bus)
    fsw.step(t_ns=2 * NS, bus=bus)

    writes = _health(decoded(station), rate_groups)

    assert writes
    assert [t for _, t, _ in writes] == sorted(t for _, t, _ in writes)
    assert {t for _, t, _ in writes} <= {NS, 2 * NS}
    for group in rate_groups:
        counts = [v for n, _, v in writes if n == f"{group}.CycleCount"]
        assert counts == list(range(1, len(counts) + 1)), group
    assert _health(decoded(station), rate_groups) == []


def test_a_write_between_whole_seconds_is_tagged_to_the_microsecond(
    fsw: ModuleType,
    station: FprimeStation,
    rate_groups: list[str],
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """A tick at 1.500007 s tags its writes with that time in ns, microseconds included.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        rate_groups: the copy's rate groups.
        decoded: drains the station's telemetry as values.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    fsw.boot(prm, parameter_ids)
    t_ns = NS + 500_000_000 + 7_000

    fsw.step(t_ns=t_ns, bus=bus)

    writes = _health(decoded(station), rate_groups)
    assert writes
    assert {t for _, t, _ in writes} == {t_ns}


def test_each_rate_group_runs_once_every_divider_ticks(
    fsw: ModuleType,
    station: FprimeStation,
    configuration: str,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """Each rate group's `CycleCount` advances by one once every divider ticks, its own divider.

    A rate group `<stem>RateGroup` runs at the constant `<stem>Divider` of the configuration's
    GNC sub-topology. The count is taken over ten of the dividers' least common multiple, a whole
    number of every divider, which holds whatever tick the driver starts on.

    Args:
        fsw: the test's copy of the deployment.
        station: the station on it.
        configuration: the copy's configuration.
        tmp_path: where the configuration's topology is rendered.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
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
