"""The structural type an algorithm satisfies to be hosted.

A hosted algorithm is built as `Algorithm(t0=..., **init)`, `t0` in s being the time its
initial state applies at; it exposes its current state as `state` and advances one sample at a
time with `step(sample)`. Its sample type is a dataclass with a field `t` (s) plus one field per
input signal; its state carries `t` (s) plus one attribute per output signal (`HostedState`).
"""

from typing import Any, Protocol

from gnc_cdh.hosted_state import HostedState

__all__ = ["HostedAlgorithm"]


class HostedAlgorithm(Protocol):
    """An algorithm a transport can host: a current `state`, and `step(sample)` advancing it
    to `sample.t` and returning the new state."""

    @property
    def state(self) -> HostedState:
        """The algorithm's current state, at the time of the latest sample stepped, or `t0`."""
        ...

    def step(self, sample: Any) -> HostedState:
        """Advances the state to `sample.t` (s) with `sample`'s input fields and returns the new
        state."""
        ...
