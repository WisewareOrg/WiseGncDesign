"""The state a hosted algorithm exposes."""

from typing import Protocol

__all__ = ["HostedState"]


class HostedState(Protocol):
    """A hosted algorithm's state at one instant: `t` in s, plus one attribute per output."""

    @property
    def t(self) -> float: ...
