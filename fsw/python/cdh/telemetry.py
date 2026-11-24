"""The Python build's raw telemetry: an algorithm's telemetry tuple, as one write per field written.

A field is a channel of the algorithm's instance, and `None` is not written, which no FPP value is.
Each write is tagged with its tick's time; the ground packs the values with the dictionary. A frame
logs a telemetry tuple whole, as an `Entry`, which the frame runner expands to writes at decode.
"""

from __future__ import annotations

import functools
from typing import Any, NamedTuple

import numpy as np

__all__ = ["Entry", "entry", "writes"]

Entry = tuple[tuple[str, ...], int, tuple[Any, ...]]
"""One telemetry tuple as logged: its channels `<instance>.<field>` in field order, the tick's time
in ns, and its values in field order, each array copied and each unwritten field `None`."""


def entry(instance: str, telemetry: NamedTuple | None, t_ns: int) -> Entry | None:
    """The log entry of one telemetry tuple, each array copied as written.

    Args:
        instance: the instance's unqualified name.
        telemetry: the `<Name>Telemetry` tuple a step or command returned, or `None`.
        t_ns: ns, the tick's time, which tags each write.

    Returns:
        `(channels, t_ns, values)`, or `None` for a `None` tuple.
    """
    if telemetry is None:
        return None
    values = tuple(value.copy() if isinstance(value, np.ndarray) else value for value in telemetry)
    return _channels(instance, telemetry._fields), t_ns, values


def writes(instance: str, telemetry: NamedTuple | None, t_ns: int) -> list[tuple[str, int, Any]]:
    """The writes of one telemetry tuple, in its fields' order, each array copied as written.

    Args:
        instance: the instance's unqualified name.
        telemetry: the `<Name>Telemetry` tuple a step or command returned, or `None`.
        t_ns: ns, the tick's time, which tags each write.

    Returns:
        `(<instance>.<channel>, t_ns, value)` for each field that is not `None`.
    """
    logged = entry(instance, telemetry, t_ns)
    if logged is None:
        return []
    channels, t_ns, values = logged
    return [(channel, t_ns, value) for channel, value in zip(channels, values, strict=True) if value is not None]


@functools.cache
def _channels(instance: str, fields: tuple[str, ...]) -> tuple[str, ...]:
    """Each field's channel, `<instance>.<field>`, named once per instance and telemetry tuple.

    Args:
        instance: the instance's unqualified name.
        fields: the telemetry tuple's fields.

    Returns:
        The channels, in the fields' order.
    """
    return tuple(f"{instance}.{field}" for field in fields)
