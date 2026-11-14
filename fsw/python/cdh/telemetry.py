"""The Python build's raw telemetry: an algorithm's telemetry tuple as one write per field written.

A field is a channel of the algorithm's instance, and `None` is not written, which no FPP value is.
The host tags each write with its tick's time; the ground packs the values with the dictionary.
"""

from typing import Any, NamedTuple

import numpy as np

__all__ = ["writes"]


def writes(instance: str, telemetry: NamedTuple | None) -> list[tuple[str, Any]]:
    """The writes of one telemetry tuple, in its fields' order, each array copied as written.

    Args:
        instance: the instance's name, such as `nav`.
        telemetry: the `<Name>Telemetry` tuple a step or command returned, or `None`.

    Returns:
        `(<instance>.<channel>, value)` for each field that is not `None`.
    """
    if telemetry is None:
        return []
    return [
        (f"{instance}.{channel}", value.copy() if isinstance(value, np.ndarray) else value)
        for channel, value in telemetry._asdict().items()
        if value is not None
    ]
