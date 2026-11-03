"""One output entry of the data dictionary."""

from dataclasses import dataclass

__all__ = ["OutputSignal"]


@dataclass(frozen=True)
class OutputSignal:
    """One state field, published as one signal of one output role.

    Attributes:
        role: the output port.
        signal: the neutral quantity published on that role.
        state_field: the attribute of the algorithm's state that supplies it.
    """

    role: str
    signal: str
    state_field: str
