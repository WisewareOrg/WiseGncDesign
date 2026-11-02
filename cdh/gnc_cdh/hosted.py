"""The structural types an algorithm and its state satisfy to be hosted.

A hosted algorithm is built as `Algorithm(t0=..., **init)`, `t0` in s being the time its
initial state applies at; it exposes its current state as `state` and advances one sample at a
time with `step(sample)`. Its sample type is a dataclass with a field `t` (s) plus one field per
input signal; its state carries `t` (s) plus one attribute per output signal.
"""

from typing import Any, Protocol, runtime_checkable

__all__ = ["HostedAlgorithm", "HostedState"]


@runtime_checkable
class HostedState(Protocol):
    """A hosted algorithm's state at one instant: `t` in s, plus one attribute per output."""

    @property
    def t(self) -> float: ...


@runtime_checkable
class HostedAlgorithm(Protocol):
    """An algorithm a transport can host: a current `state`, and `step(sample)` advancing it
    to `sample.t` and returning the new state."""

    @property
    def state(self) -> HostedState: ...

    def step(self, sample: Any) -> HostedState: ...
