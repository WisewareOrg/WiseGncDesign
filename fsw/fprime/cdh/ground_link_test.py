"""`Cdh.GroundLink` holds its downlink and its command responses in storage fixed at boot.

Flown on the test mock `MockActuation` through `lab.Adapter`, whose `frames` is the base ticks of
telemetry the downlink holds undrained, each channel written once per base tick. A flight held to
`frames` ticks loses no write, however long; a downlink past its storage trips F´'s assert, which
raises in Python, and never drops, overwrites or grows. 256 command responses are held undrained;
the 257th trips the assert. Skipped without the deployment `just fsw` builds, as `mock_actuation`
skips.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.mock import MOCK
from ground.fprime_station import FprimeStation
from lab import Adapter

NS = 1_000_000_000
"""ns per s."""

_GROUND_LINK = r'^Assert: "[^"]*fsw/fprime/cdh/GroundLink\.cpp:\d+"'
"""An assert GroundLink's own checks raise."""

_RESPONSES = 256
"""The command responses GroundLink holds undrained."""

_COUNT = "actuationRateGroup.CycleCount"
"""A channel the test mock's rate group writes every other base tick, counting 1, 2, ..."""

_MOCK_ACTUATION = "MockActuation"


def _flown(record: Path, frames: int) -> tuple[Adapter, FprimeStation]:
    """MockActuation's adapter booted to hold `frames` ticks of telemetry, and its station.

    Args:
        record: the case's parameter record.
        frames: the base ticks of telemetry the downlink holds undrained.

    Returns:
        The adapter and the ground station on its pins.
    """
    adapter = Adapter(_MOCK_ACTUATION, record, contract=MOCK, frames=frames)
    adapter.boot()
    return adapter, FprimeStation(adapter, adapter.dictionary)


@pytest.mark.parametrize("frames", [2, 8, 10_000], ids=["two", "eight", "past-8175"])
def test_a_flight_held_to_its_frames_loses_no_telemetry_write_undrained(
    mock_actuation: tuple[str, Any, Any, Path], frames: int
) -> None:
    """`frames` ticks flown with no drain between come down whole, every write in order.

    The rate group counts 1, 2, ... once every other tick, so a write lost anywhere in the
    downlink, or one the storage dropped at its capacity, leaves a gap or a short count. 10,000
    ticks is past the 8,175 a fixed 4,096 packets held of a flight.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
        frames: the base ticks flown, and the downlink's frames.
    """
    _, _, _, record = mock_actuation
    adapter, station = _flown(record, frames)

    for k in range(1, frames + 1):
        adapter.tick(k * NS, {})

    counts = station.decode([station.telemetry()], [_COUNT])[_COUNT].values
    assert counts.tolist() == list(range(1, frames // 2 + 1))


def test_a_downlink_past_its_storage_asserts_without_losing_what_is_stored(
    mock_actuation: tuple[str, Any, Any, Path],
) -> None:
    """With one frame of storage, a flight undrained asserts within 1,000 ticks, keeping every stored write.

    The assert is F´'s, raised in Python from the tick whose write finds the storage full. One
    `telemetry` then gives every write of the ticks before the tripping tick T, the open packet's
    included, as an adapter with room for the whole flight downlinks them, and of the writes tagged
    T a prefix of that flight's. The tick the assert comes at is not fixed.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
    """
    _, _, _, record = mock_actuation
    small, small_station = _flown(record, 1)
    flown = 0
    with pytest.raises(RuntimeError, match=_GROUND_LINK):
        for k in range(1, 1_001):
            flown = k
            small.tick(k * NS, {})
    assert flown > 1

    kept = small_station.decode([small_station.telemetry()])
    whole, whole_station = _flown(record, flown)
    for k in range(1, flown + 1):
        whole.tick(k * NS, {})
    expected = whole_station.decode([whole_station.telemetry()])

    tripped = flown * NS
    for name, reference in expected.items():
        before = reference.times < tripped
        at = np.flatnonzero(reference.times == tripped)
        got = kept.get(name)
        times = np.empty(0, np.int64) if got is None else got.times
        values = np.empty((0, *np.asarray(reference.values).shape[1:])) if got is None else np.asarray(got.values)
        done = int(before.sum())
        assert times[:done].tolist() == reference.times[:done].tolist(), name
        assert np.array_equal(values[:done], np.asarray(reference.values)[:done]), name
        later = len(times) - done
        assert 0 <= later <= len(at), name
        assert times[done:].tolist() == reference.times[done : done + later].tolist(), name
        assert np.array_equal(values[done:], np.asarray(reference.values)[done : done + later]), name


def _respond(station: FprimeStation, adapter: Adapter, contexts: range) -> None:
    """Uplinks `cmdDisp.CMD_NO_OP` under each context, a tick after each, draining nothing.

    Args:
        station: the station on the adapter.
        adapter: the adapter.
        contexts: the ground's numbers for the commands, one command and one tick each.
    """
    for context in contexts:
        station.uplink("cmdDisp.CMD_NO_OP", {}, context)
        adapter.tick((context + 1) * NS, {})


def test_256_command_responses_are_held_undrained_in_order(mock_actuation: tuple[str, Any, Any, Path]) -> None:
    """256 responses undrained all come down, oldest first, and a drain empties the store.

    A second 256 after the drain holds as well, so the store is emptied, not worn out.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
    """
    _, _, _, record = mock_actuation
    adapter, station = _flown(record, 1_000)

    _respond(station, adapter, range(_RESPONSES))
    assert station.responses() == [(context, "OK", None) for context in range(_RESPONSES)]
    assert station.responses() == []

    _respond(station, adapter, range(1_000, 1_000 + _RESPONSES))
    assert station.responses() == [(context, "OK", None) for context in range(1_000, 1_000 + _RESPONSES)]


def test_the_257th_undrained_command_response_asserts(mock_actuation: tuple[str, Any, Any, Path]) -> None:
    """The response past the 256 held trips F´'s assert in the tick that runs its command.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
    """
    _, _, _, record = mock_actuation
    adapter, station = _flown(record, 1_000)
    _respond(station, adapter, range(_RESPONSES))

    station.uplink("cmdDisp.CMD_NO_OP", {}, _RESPONSES)
    with pytest.raises(RuntimeError, match=_GROUND_LINK):
        adapter.tick((_RESPONSES + 1) * NS, {})
