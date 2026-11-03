"""One output of a hosted algorithm: a state field written to a payload field."""

from dataclasses import dataclass

__all__ = ["OutputMap"]


@dataclass(frozen=True)
class OutputMap:
    """One payload field of one output message, written from one state field.

    Attributes:
        state_field: the attribute of the algorithm's state that supplies the value.
        output: the name of the output message in `AlgorithmModule.output_messages`.
        payload_field: the field of that message's payload.
    """

    state_field: str
    output: str
    payload_field: str
