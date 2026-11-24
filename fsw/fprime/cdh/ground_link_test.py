"""`Cdh.GroundLink` holds its downlink and its command responses in storage fixed at boot.

Flown on the test mock `MockActuation` through `lab.Adapter`, whose `frames` is the base ticks of
telemetry the downlink holds undrained, each channel written once per base tick. A flight its
frames hold loses no write; a downlink past its storage trips F´'s assert, which raises in Python,
and never drops, overwrites or grows. 256 command responses are held undrained; the 257th trips the
assert. Skipped without the deployment `just fsw` builds, as `mock_actuation` skips.
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

_TALLY = "actuator.tally"
"""A channel the test mock writes at each step and each `actuator.mark`, counting 1, 2, ..."""

_MARKS = 9
"""The marks a marked tick uplinks, about a frame's bytes."""

_FITS = pytest.mark.parametrize(("frames", "ticks"), [(11, 25), (1_000, 2_066)])
"""A downlink's frames, and the most ticks of `_MARKS` marks it holds undrained.

A frame is MockActuation's 9 channels, 243 bytes: each a 4-byte ID, an 11-byte time tag and its
value. A packet carries 510 bytes of entries, so any two neighbours carry more than 510 between
them, and `frames` take at most `2 * frames * 243 // 510 + 1` packets. The storage has one more,
the drain's: 12 packets for 11 frames and 954 for 1,000, each one more than a frame fewer has. The
flights write 12 and 954 packets. The mock's entries, 55 bytes at most, pack nearly whole packets
where the bound allows half-full ones, so the flights are twice `frames` ticks long.
"""


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

    def fly(self, ticks: int, marks: int = 0) -> None:
        """Flies more ticks, draining the marks' responses alone.

        Args:
            ticks: how many.
            marks: the `actuator.mark` commands uplinked before each.
        """
        for _ in range(ticks):
            for context in range(marks):
                self._station.uplink("actuator.mark", {}, context)
            self.ticks += 1
            self._adapter.tick(self.ticks * NS, {})
            if marks:
                self._station.responses()

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

    @_FITS
    def test_the_most_a_downlink_s_frames_hold_comes_down_whole(self, frames: int, ticks: int) -> None:
        """Every write of the longest marked flight the downlink holds undrained comes down, in order.

        The tally counts the marks and the mock's steps, one every other tick from the first, and
        the rate group counts its cycles, so a write lost anywhere leaves a gap or a short count.

        Args:
            frames: the downlink's frames.
            ticks: the ticks flown.
        """
        flight = Flight(self.record, frames)
        steps = (ticks + 1) // 2

        flight.fly(ticks, _MARKS)

        writes = flight.writes()
        tallies = [write.value for write in writes[_TALLY]]
        counts = [write.value for write in writes[_COUNT]]
        expected = ticks * _MARKS + steps
        assert tallies == list(range(1, expected + 1)), f"{len(tallies)} tallies of {expected}, or out of order"
        assert counts == list(range(1, steps + 1)), f"{len(counts)} counts of {steps}, or out of order"

    @_FITS
    def test_a_downlink_of_one_frame_fewer_asserts(self, frames: int, ticks: int) -> None:
        """The flight `frames` just hold trips the assert of a downlink of one frame fewer.

        Args:
            frames: the frames that hold the flight.
            ticks: the ticks flown.
        """
        flight = Flight(self.record, frames - 1)

        with pytest.raises(RuntimeError, match=_GROUND_LINK):
            flight.fly(ticks, _MARKS)

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
