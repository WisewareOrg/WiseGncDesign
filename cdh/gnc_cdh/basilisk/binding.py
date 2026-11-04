"""`Binding`: one algorithm's declaration of what it reads and writes.

Both are named as Basilisk message fields.
"""

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["Binding"]


@dataclass(frozen=True)
class Binding:
    """One algorithm's declaration of what it reads and what it writes.

    Attributes:
        algorithm: the algorithm class, built as `algorithm(t0=..., **init)`. Its `step(t=...,
            **inputs)` takes plain arrays by keyword and returns plain named arrays, and it holds
            each output name as an attribute, together with `t` (s).
        inputs: `step` keyword to the `(input role, message field)` it is copied from.
        outputs: returned name to the `(output message, message field)` it is copied to.
        messages: output message name to its Basilisk message type.
    """

    algorithm: type
    inputs: Mapping[str, tuple[str, str]]
    outputs: Mapping[str, tuple[str, str]]
    messages: Mapping[str, type]
