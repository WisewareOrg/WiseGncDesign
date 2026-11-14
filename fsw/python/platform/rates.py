"""The Python build's rate-group driver, counting base ticks as F´'s `Svc.RateGroupDriver` does."""

from collections.abc import Sequence

__all__ = ["RateGroupDriver"]


class RateGroupDriver:
    """Says which rate groups run at each base tick, by their driver's `CycleOut` index.

    As F´'s driver, with every offset 0: a rate group runs when its divider divides the tick count,
    which starts at 0, so the first tick runs every rate group, and rolls over at the product of
    the dividers; a divider of 0 never runs its rate group and is left out of the product.
    """

    def __init__(self, dividers: Sequence[int]) -> None:
        """Starts the tick count at 0.

        Args:
            dividers: each rate group's divider, by its `CycleOut` index.
        """
        self._dividers = tuple(dividers)
        self._rollover = 1
        for divider in self._dividers:
            if divider:
                self._rollover *= divider
        self._ticks = 0

    def tick(self) -> list[int]:
        """Counts one base tick.

        Returns:
            The `CycleOut` index of each rate group that runs at it, in order.
        """
        fired = [i for i, d in enumerate(self._dividers) if d and self._ticks % d == 0]
        self._ticks = (self._ticks + 1) % self._rollover
        return fired
