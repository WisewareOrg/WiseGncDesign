"""The Python build's raw telemetry: an algorithm's telemetry tuple as one write per field written.

A field is a channel of the algorithm's instance, and `None` is not written, which no FPP value is.
`GroundLink` tags each write with its tick's time; the ground packs the values with the
dictionary.
"""

from __future__ import annotations

import functools
from typing import Any, NamedTuple

import numpy as np

__all__ = ["writes"]


def writes(instance: str, telemetry: NamedTuple | None) -> list[tuple[str, Any]]:
    """The writes of one telemetry tuple, in its fields' order, each array copied as written.

    Args:
        instance: the instance's unqualified name.
        telemetry: the `<Name>Telemetry` tuple a step or command returned, or `None`.

    Returns:
        `(<instance>.<channel>, value)` for each field that is not `None`.
    """
    if telemetry is None:
        return []
    return [
        (channel, value.copy() if isinstance(value, np.ndarray) else value)
        for channel, value in zip(_channels(instance, telemetry._fields), telemetry, strict=True)
        if value is not None
    ]


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
