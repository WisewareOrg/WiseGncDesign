"""One input entry of the data dictionary."""

from dataclasses import dataclass

__all__ = ["InputSignal"]


@dataclass(frozen=True)
class InputSignal:
    """One sample field, fed from one signal of one input role.

    Attributes:
        role: the input port, e.g. one sensor.
        signal: the neutral quantity read from that role.
        sample_field: the field of the algorithm's sample type that receives it.
        frame: the name of a transform in `gnc_cdh.frames.TRANSFORMS` the host applies with
            that role's mounting, or `None` for the value as read.
    """

    role: str
    signal: str
    sample_field: str
    frame: str | None = None
