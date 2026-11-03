"""One input of a hosted algorithm: a payload field read into a sample field."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

__all__ = ["InputMap"]


@dataclass(frozen=True)
class InputMap:
    """One sample field, read from one payload field of one input.

    Attributes:
        input: the name of the input reader in `AlgorithmModule.inputs`.
        payload_field: the field of that reader's payload.
        sample_field: the field of the sample type that receives the value.
        transform: applied to the value, as a float array, before it reaches the sample; `None`
            passes it as read.
    """

    input: str
    payload_field: str
    sample_field: str
    transform: Callable[[np.ndarray], np.ndarray] | None = None
