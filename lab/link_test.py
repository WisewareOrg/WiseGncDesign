"""The deployment's pins through the ground station: commands up, responses and telemetry down.

The command is F´'s own `cmdDisp.CMD_NO_OP`, and the writes are each `Svc.PassiveRateGroup`'s
health channels, which every deployment has. Skipped without the deployment `just fsw` builds.
"""

import math
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from fsw.codegen.deployment import fpp_files
from fsw.codegen.fpp_model import read
from ground.fprime_station import FprimeStation

NS = 1_000_000_000
"""ns per s."""


def _health(writes: list[tuple[str, int, Any]], rate_groups: list[str]) -> list[tuple[str, int, Any]]:
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


def test_a_packet_larger_than_f_prime_s_buffer_is_refused_naming_its_size(fsw: ModuleType):
    """`uplink` refuses a packet too large for the command buffer, before the dispatcher sees it.

    Args:
        fsw: the test's copy of the deployment.
    """
    with pytest.raises(ValueError, match="packet of 10000 bytes exceeds"):
        fsw.uplink(bytes(10_000), 1)


def test_the_rate_groups_writes_come_down_once_in_order_with_their_f_prime_time(
    booted: ModuleType,
    station: FprimeStation,
    rate_groups: list[str],
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    bus: list[tuple[int, bytes]],
):
    """Each rate group's writes of two ticks come down in the order written, tagged with each tick.

    Every write of the first tick comes before every write of the second. The first tick is at
    1.500007 s, so its writes are tagged with that time in ns, microseconds included.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        station: the station on it.
        rate_groups: the copy's rate groups.
        decoded: drains the station's telemetry as values.
        bus: every role's bus message on its LabBusDriver port.
    """
    first = NS + 500_000_000 + 7_000
    booted.step(t_ns=first, bus=bus)
    booted.step(t_ns=2 * NS, bus=bus)

    writes = _health(decoded(station), rate_groups)

    assert writes
    assert [t for _, t, _ in writes] == sorted(t for _, t, _ in writes)
    assert {t for _, t, _ in writes} <= {first, 2 * NS}
    assert first in {t for _, t, _ in writes}
    assert _health(decoded(station), rate_groups) == []


def test_each_rate_group_runs_once_every_divider_ticks(
    booted: ModuleType,
    station: FprimeStation,
    configuration: str,
    tmp_path: Path,
    bus: list[tuple[int, bytes]],
):
    """Each rate group's `CycleCount` advances by one once every divider ticks, its own divider.

    A rate group `<stem>RateGroup` runs at the constant `<stem>Divider` of the configuration's
    GNC sub-topology. The count is taken over ten of the dividers' least common multiple, a whole
    number of every divider, which holds whatever tick the driver starts on.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        station: the station on it.
        configuration: the copy's configuration.
        tmp_path: where the configuration's topology is rendered.
        bus: every role's bus message on its LabBusDriver port.
    """
    constants = read(fpp_files(configuration, tmp_path)).constants
    dividers = {
        name.removeprefix(f"{configuration}.").removesuffix("Divider") + "RateGroup": int(divider)
        for name, divider in constants.items()
        if name.startswith(f"{configuration}.") and name.endswith("Divider")
    }
    assert dividers
    ticks = 10 * math.lcm(*dividers.values())
    station.telemetry()

    for tick in range(1, ticks + 1):
        booted.step(t_ns=tick * NS, bus=bus)

    writes = station.telemetry()
    for group, divider in dividers.items():
        name = f"{group}.CycleCount"
        counts = station.values(name, [raw for written, _, raw in writes if written == name])
        assert len(counts) == ticks // divider, group
        assert np.diff(counts).tolist() == [1] * (len(counts) - 1), group


def test_the_pump_raises_naming_a_queue_its_bound_leaves_holding_messages(
    booted: ModuleType,
    station: FprimeStation,
):
    """A queue still holding messages after the pump's rounds raises, naming it, never hangs.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        station: the station on it.
    """
    station.uplink("cmdDisp.CMD_NO_OP", {}, 3)

    with pytest.raises(RuntimeError, match=r"queue WiseFsw\.cmdDisp did not drain: messages left 1, rounds 1$"):
        booted.pump(rounds=1)
    booted.pump()

    assert _responses(station) == [(3, "OK")]
