"""The Python build's CDH logs an algorithm's telemetry tuple as one write per field written."""

from collections import namedtuple

import numpy as np

from fsw.python.cdh import telemetry

Telemetry = namedtuple("Telemetry", ["mode", "position", "count"], defaults=[None] * 3)
"""A telemetry tuple."""


def test_each_field_written_is_one_write_named_for_its_instance_in_field_order():
    """A `None` field is not written; an array is copied as written."""
    position = np.array([1.0, 2.0, 3.0])

    writes = telemetry.writes("nav", Telemetry(position=position, count=0, mode="fast"))
    position[0] = 9.0

    assert [name for name, _ in writes] == ["nav.mode", "nav.position", "nav.count"]
    assert writes[0][1] == "fast"
    np.testing.assert_array_equal(writes[1][1], [1.0, 2.0, 3.0])
    assert writes[2][1] == 0
    assert [name for name, _ in telemetry.writes("nav", Telemetry(count=1))] == ["nav.count"]


def test_nothing_returned_writes_nothing():
    """A handler returning `None` writes no telemetry."""
    assert telemetry.writes("nav", None) == []
