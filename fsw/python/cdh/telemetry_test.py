"""The Python build's CDH logs an algorithm's telemetry tuple as one write per field written."""

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


def test_each_field_written_is_one_write_named_for_its_instance_in_field_order():
    """Each write is tagged with the time given; a `None` field is not written; an array is copied."""
    position = np.array([1.0, 2.0, 3.0])

    writes = telemetry.writes("mock", Telemetry(position=position, count=0, mode="fast"), 7)
    position[0] = 9.0

    assert [(name, t) for name, t, _ in writes] == [("mock.mode", 7), ("mock.position", 7), ("mock.count", 7)]
    assert writes[0][2] == "fast"
    np.testing.assert_array_equal(writes[1][2], [1.0, 2.0, 3.0])
    assert writes[2][2] == 0
    assert [name for name, _, _ in telemetry.writes("mock", Telemetry(count=1), 7)] == ["mock.count"]


def test_an_entry_names_the_channels_and_keeps_the_values_with_their_arrays_copied():
    """An entry is `(channels, t_ns, values)`: `<instance>.<field>` names and values in field order.

    A `None` field stays `None`; an array is copied as written, so a later edit is not seen.
    """
    position = np.array([1.0, 2.0, 3.0])

    entry = telemetry.entry("mock", Telemetry(position=position, mode="fast"), 7)
    position[0] = 9.0

    assert entry is not None
    channels, t_ns, values = entry
    assert channels == ("mock.mode", "mock.position", "mock.count")
    assert t_ns == 7
    assert len(values) == 3
    assert values[0] == "fast"
    assert values[2] is None
    assert values[1] is not position
    np.testing.assert_array_equal(values[1], [1.0, 2.0, 3.0])


def test_no_telemetry_is_no_entry():
    """A step or command that wrote no tuple logs nothing."""
    assert telemetry.entry("mock", None, 7) is None
