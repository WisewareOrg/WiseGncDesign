"""Where the Basilisk transport reads one input signal."""

from typing import NamedTuple

__all__ = ["InputField"]


class InputField(NamedTuple):
    """Where an input signal is read: a reader of type `reader_type`, field `payload_field`."""

    reader_type: type
    payload_field: str
