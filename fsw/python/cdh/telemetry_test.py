"""The Python build's CDH logs an algorithm's telemetry tuple as one entry, which expands to writes."""

from typing import Any, NamedTuple

import numpy as np

from fsw.python.cdh import telemetry


class Telemetry(NamedTuple):
    """A telemetry tuple.

    Attributes:
        mode: the mode, or `None`.
        position: the position, or `None`.
        count: the count, or `None`.
    """

    mode: Any = None
    position: Any = None
    count: Any = None


def test_an_entry_is_the_instance_the_time_and_the_tuple_with_its_arrays_copied():
    """The tuple keeps its type and values; an array is copied as written, so a later edit is not seen."""
    position = np.array([1.0, 2.0, 3.0])
    written = Telemetry(position=position, count=0, mode="fast")

    entry = telemetry.entry("mock", written, 7)
    position[0] = 9.0

    assert entry is not None
    instance, t_ns, logged = entry
    assert (instance, t_ns) == ("mock", 7)
    assert type(logged) is Telemetry
    assert logged.mode == "fast"
    assert logged.count == 0
    assert logged.position is not position
    np.testing.assert_array_equal(logged.position, [1.0, 2.0, 3.0])


def test_no_telemetry_is_no_entry():
    """A step or command that wrote no tuple logs nothing."""
    assert telemetry.entry("mock", None, 7) is None


def test_entries_expand_to_writes_in_entry_then_field_order_skipping_none_fields():
    """Each entry's fields are its writes, named for its instance and tagged with its time.

    A `None` field is not written; an all-`None` tuple expands to nothing.
    """
    position = np.array([1.0, 2.0, 3.0])
    entries = [
        telemetry.entry("mock", Telemetry(position=position, count=0, mode="fast"), 7),
        telemetry.entry("other", Telemetry(count=1), 7),
        telemetry.entry("mock", Telemetry(), 8),
        telemetry.entry("mock", Telemetry(count=2), 9),
    ]

    writes = telemetry.writes([e for e in entries if e is not None])

    assert [(name, t) for name, t, _ in writes] == [
        ("mock.mode", 7),
        ("mock.position", 7),
        ("mock.count", 7),
        ("other.count", 7),
        ("mock.count", 9),
    ]
    assert writes[0][2] == "fast"
    np.testing.assert_array_equal(writes[1][2], [1.0, 2.0, 3.0])
    assert [value for _, _, value in writes[2:]] == [0, 1, 2]


def test_no_entries_expand_to_no_writes():
    """Nothing logged, nothing written."""
    assert telemetry.writes([]) == []
