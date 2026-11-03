"""Where the Basilisk transport writes one output signal."""

from typing import NamedTuple

__all__ = ["OutputField"]


class OutputField(NamedTuple):
    """Where an output signal is written: field `payload_field` of the output message named
    `message`, of type `message_type`."""

    message: str
    message_type: type
    payload_field: str
