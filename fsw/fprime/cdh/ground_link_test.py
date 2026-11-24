"""`Cdh.GroundLink` holds its downlink and its command responses in storage fixed at boot.

Flown on the test mock `MockActuation` through `lab.Adapter`, whose `frames` is the base ticks of
telemetry the downlink holds undrained, each channel written once per base tick. A flight held to
`frames` ticks loses no write, however long; a downlink past its storage trips F´'s assert, which
raises in Python, and never drops, overwrites or grows. 256 command responses are held undrained;
the 257th trips the assert. Skipped without the deployment `just fsw` builds, as `mock_actuation`
skips.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np
import pytest

from fsw.mock import MOCK
from ground.fprime_station import FprimeStation
from lab import Adapter

if TYPE_CHECKING:
    from conftest import MockActuationCase

NS = 1_000_000_000
"""ns per s."""

_GROUND_LINK = r'^Assert: "[^"]*fsw/fprime/cdh/GroundLink\.cpp:\d+"'
"""An assert GroundLink's own checks raise."""

_RESPONSES = 256
"""The command responses GroundLink holds undrained."""

_COUNT = "actuationRateGroup.CycleCount"
"""A channel the test mock's rate group writes every other base tick, counting 1, 2, ..."""


class Write(NamedTuple):
    """One telemetry write of a channel.

    Attributes:
        t_ns: ns, its time tag.
        value: its value, as plain lists.
    """

    t_ns: int
    value: Any


Writes = dict[str, list[Write]]
"""Each channel's writes, in the order downlinked."""


class Flight:
    """A copy of MockActuation and the ground station on it, flown without draining.

    Attributes:
        ticks: the ticks flown, the last one's number.
    """

    ticks: int

    def __init__(self, record: Path, frames: int) -> None:
        """Boots a copy.

        Args:
            record: the case's parameter record.
            frames: the base ticks of telemetry its downlink holds undrained.
        """
        self._adapter = Adapter("MockActuation", record, contract=MOCK, frames=frames)
        self._adapter.boot()
        self._station = FprimeStation(self._adapter, self._adapter.dictionary)
        self.ticks = 0

    def fly(self, ticks: int) -> None:
        """Flies more ticks.

        Args:
            ticks: how many.
        """
        for _ in range(ticks):
            self.ticks += 1
            self._adapter.tick(self.ticks * NS, {})

    def command(self, contexts: Iterable[int]) -> None:
        """Uplinks `cmdDisp.CMD_NO_OP` under each context, and flies a tick after each.

        Args:
            contexts: the ground's numbers for the commands.
        """
        for context in contexts:
            self._station.uplink("cmdDisp.CMD_NO_OP", {}, context)
            self.fly(1)

    def responses(self) -> list[tuple[int, str, str | None]]:
        """Drains the command responses.

        Returns:
            Each response, as the station gives it, oldest first.
        """
        return self._station.responses()

    def writes(self) -> Writes:
        """Drains the telemetry.

        Returns:
            Each channel's writes.
        """
        return {
            channel: [Write(*write) for write in zip(times.tolist(), np.asarray(values).tolist(), strict=True)]
            for channel, (times, values) in self._station.decode([self._station.telemetry()]).items()
        }


def _tagged(writes: Writes, wanted: Callable[[int], bool]) -> Writes:
    """The writes whose time tag is wanted.

    Args:
        writes: each channel's writes.
        wanted: whether a time tag, ns, is.

    Returns:
        Those writes, of each channel that has any.
    """
    kept = {channel: [write for write in each if wanted(write.t_ns)] for channel, each in writes.items()}
    return {channel: each for channel, each in kept.items() if each}


def _accepted(contexts: Iterable[int]) -> list[tuple[int, str, str | None]]:
    """The responses of commands accepted.

    Args:
        contexts: the commands' contexts, in order.

    Returns:
        Each response, as the station gives it.
    """
    return [(context, "OK", None) for context in contexts]


class TestGroundLink:
    """GroundLink's fixed storage, flown on MockActuation."""

    @pytest.fixture(autouse=True)
    def _record(self, mock_actuation: MockActuationCase) -> None:
        """Holds the case's parameter record, on which each flight boots.

        Args:
            mock_actuation: the configuration and its record.
        """
        self.record = mock_actuation.record

    @pytest.mark.parametrize("frames", [2, 8, 10_000])
    def test_a_flight_held_to_its_frames_loses_no_telemetry_write_undrained(self, frames: int) -> None:
        """`frames` ticks flown with no drain between come down whole, every write in order.

        The rate group counts 1, 2, ... once every other tick, so a write lost anywhere in the
        downlink, or one the storage dropped at its capacity, leaves a gap or a short count.

        Args:
            frames: the base ticks flown, and the downlink's frames.
        """
        flight = Flight(self.record, frames)

        flight.fly(frames)

        counts = [write.value for write in flight.writes()[_COUNT]]
        assert counts == list(range(1, frames // 2 + 1)), f"{len(counts)} counts of {frames // 2}, or out of order"

    def test_a_downlink_past_its_storage_asserts_without_losing_what_is_stored(self) -> None:
        """With one frame of storage, a flight undrained asserts within 1,000 ticks, keeping every stored write.

        The assert is F´'s, raised in Python from the tick whose write finds the storage full. One
        drain then gives every write of the ticks before the tripping tick T, the open packet's
        included, as an adapter with room for the whole flight downlinks them, and of each channel's
        writes tagged T a prefix of that flight's. The tick the assert comes at is not fixed.
        """
        roomy = Flight(self.record, frames=1_000)
        roomy.fly(1_000)
        whole = roomy.writes()
        flight = Flight(self.record, frames=1)

        with pytest.raises(RuntimeError, match=_GROUND_LINK):
            flight.fly(1_000)
        kept = flight.writes()

        tripping = flight.ticks * NS
        before, expected = _tagged(kept, lambda t: t < tripping), _tagged(whole, lambda t: t < tripping)
        since, at = _tagged(kept, lambda t: t >= tripping), _tagged(whole, lambda t: t == tripping)
        changed = [channel for channel in expected if before.get(channel) != expected[channel]]
        unwritten = {channel: each for channel, each in since.items() if each != at.get(channel, [])[: len(each)]}
        assert flight.ticks > 1, f"the one frame stored trips the assert at tick {flight.ticks}, not after it"
        assert before == expected, f"{changed} lost or changed a write tagged before tick {flight.ticks}"
        assert not unwritten, f"the tripping tick keeps {unwritten}, not a prefix of the writes {at}"

    def test_256_command_responses_are_held_undrained_in_order(self) -> None:
        """256 responses undrained all come down, oldest first."""
        flight = Flight(self.record, frames=1_000)

        flight.command(range(_RESPONSES))

        held = flight.responses()
        assert held == _accepted(range(_RESPONSES)), f"{len(held)} responses of {_RESPONSES}, or out of order"

    def test_a_drain_of_256_command_responses_makes_room_for_256_more(self) -> None:
        """A drain empties the store, and the 256 responses after it all come down."""
        flight = Flight(self.record, frames=1_000)
        flight.command(range(_RESPONSES))
        later = range(1_000, 1_000 + _RESPONSES)

        flight.responses()
        left = flight.responses()
        flight.command(later)

        held = flight.responses()
        assert left == [], f"{len(left)} responses are left by a drain"
        assert held == _accepted(later), f"{len(held)} responses of {_RESPONSES}, or out of order"

    def test_the_257th_undrained_command_response_asserts_without_losing_the_256(self) -> None:
        """The response past the 256 held trips F´'s assert in the tick that runs its command; the 256 come down."""
        flight = Flight(self.record, frames=1_000)
        flight.command(range(_RESPONSES))

        with pytest.raises(RuntimeError, match=_GROUND_LINK):
            flight.command([_RESPONSES])

        held = flight.responses()
        assert held == _accepted(range(_RESPONSES)), f"{len(held)} responses of {_RESPONSES}, or out of order"
