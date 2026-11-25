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
from fsw.codegen.roles import Role
from fsw.mock import MOCK
from ground.fprime_station import FprimeStation
from lab import Adapter

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


def test_each_frame_s_rate_group_writes_are_downlinked_within_its_step(
    booted: ModuleType,
    station: FprimeStation,
    rate_groups: list[str],
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    configuration: str,
    bus: list[tuple[int, bytes]],
    wire: Callable[..., Callable[..., int]],
):
    """After each step, its frame's rate group writes are down, each tagged with that frame's time.

    The first frame is at 1.500007 s, so its writes are tagged with that time in ns, microseconds
    included. Nothing of a frame is left to come down after the step that ran it.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        station: the station on it.
        rate_groups: the copy's rate groups.
        decoded: drains the station's telemetry as values.
        configuration: the copy's configuration.
        bus: every role's bus message on its LabBusDriver port.
        wire: wires the copy to the bus.
    """
    first = NS + 500_000_000 + 7_000
    step = wire(booted, configuration, bus)

    step(first)
    writes = _health(decoded(station), rate_groups)
    assert writes
    assert {t for _, t, _ in writes} == {first}

    step(2 * NS)
    writes = _health(decoded(station), rate_groups)
    assert writes
    assert {t for _, t, _ in writes} == {2 * NS}
    assert _health(decoded(station), rate_groups) == []


def test_each_rate_group_runs_once_every_divider_ticks(
    booted: ModuleType,
    station: FprimeStation,
    configuration: str,
    tmp_path: Path,
    bus: list[tuple[int, bytes]],
    wire: Callable[..., Callable[..., int]],
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
        wire: wires the copy to the bus.
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

    step = wire(booted, configuration, bus)
    for tick in range(1, ticks + 1):
        step(tick * NS)

    downlinked = station.decode([station.telemetry()])
    for group, divider in dividers.items():
        name = f"{group}.CycleCount"
        _, counts = downlinked[name]
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


class TestOneStepOfSeveralPackets:
    """One step in which eight marks each write a channel nearly a packet wide."""

    MARKS = 8

    @pytest.fixture(autouse=True)
    def _step(self, mock_actuation: tuple[str, Role, Any, Path]) -> None:
        """Steps `MockActuation` once with every mark uplinked, and drains it.

        Args:
            mock_actuation: the configuration, its role, the Python build's command and the record.
        """
        configuration, _, _, record = mock_actuation
        adapter = Adapter(configuration, record, contract=MOCK)
        adapter.boot()
        self.station = FprimeStation(adapter, adapter.dictionary)
        for mark in range(1, self.MARKS + 1):
            self.station.uplink("actuator.mark", {}, mark)
        adapter.tick(NS, {})
        self.downlink = adapter.telemetry()

    def test_every_write_comes_down_once_in_the_order_written(self):
        """The step closes at least three packets, and the marks' writes come down whole, first to last."""
        _, sizes = self.downlink
        assert len(np.frombuffer(sizes, np.uint32)) >= 3, "the step fills several packets"

        writes = self.station.decode([self.downlink], ["actuator.tally", "actuator.wide"])
        times, wide = writes["actuator.wide"]
        _, tallies = writes["actuator.tally"]
        assert wide.tolist() == [(1000.0 * mark + np.arange(50)).tolist() for mark in range(1, self.MARKS + 1)], (
            "each mark's wide value comes down once, in order"
        )
        assert tallies.tolist() == list(range(1, self.MARKS + 2)), "the marks' tallies and the step's keep their order"
        assert times.tolist() == [NS] * self.MARKS, "every write carries the step's time"
