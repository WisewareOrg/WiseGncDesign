"""What one dataset of a run file must be, and the field helper the channel classes declare
their datasets with."""

from dataclasses import field
from typing import Any, NamedTuple

__all__ = ["Dataset", "channel"]


class Dataset(NamedTuple):
    """What one dataset must be: float64, carrying a string attr `units` equal to `units`, of
    shape `(N,)` when `width` is `None` and `(N, width)` otherwise, `N` being `len(t_s)`."""

    units: str
    width: int | None


def channel(units: str, width: int | None = 3) -> Any:
    """A dataclass field declaring a dataset of `units`, `(N,)` when `width` is `None` and
    `(N, width)` otherwise."""
    return field(metadata={"units": units, "width": width})
