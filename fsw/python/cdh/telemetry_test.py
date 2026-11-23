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
