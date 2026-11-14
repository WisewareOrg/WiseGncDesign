"""The Python build's rate-group driver, counting base ticks as F´'s `Svc.RateGroupDriver` does."""

import math
from collections.abc import Sequence

from fsw.codegen.fpp_model import Model

__all__ = ["RateGroupDriver", "dividers"]


class RateGroupDriver:
    """Says which rate groups run at each base tick, by their position among its dividers.

    As F´'s driver, with every offset 0: a rate group runs when its divider divides the tick count,
    which starts at 0, so the first tick runs every rate group, and rolls over at the product of
    the dividers; a divider of 0 never runs its rate group and is left out of the product.
    """

    def __init__(self, dividers: Sequence[int]) -> None:
        """Starts the tick count at 0.

        Args:
            dividers: each rate group's divider, in its driver's `CycleOut` order.
        """
        self._dividers = tuple(dividers)
        self._rollover = math.prod(d for d in self._dividers if d)
        self._ticks = 0

    def tick(self) -> list[int]:
        """Counts one base tick.

        Returns:
            The position among the dividers of each rate group that runs at it, in order.
        """
        fired = [i for i, d in enumerate(self._dividers) if d and self._ticks % d == 0]
        self._ticks = (self._ticks + 1) % self._rollover
        return fired


def dividers(model: Model, rate_groups: Sequence[str]) -> tuple[int, ...]:
    """Each rate group's divider: `<stem>RateGroup` takes the constant `<stem>Divider`.

    The constant is in the rate group's own module, as `navRateGroup` takes `navDivider`.

    Args:
        model: the model holding the rate groups and the constants.
        rate_groups: the rate groups' qualified names, in their driver's `CycleOut` order.

    Returns:
        Their dividers, in that order.

    Raises:
        KeyError: a rate group's divider constant is not in the model, naming it.
    """
    found = []
    for group in rate_groups:
        constant = group.removesuffix("RateGroup") + "Divider"
        if constant not in model.constants:
            raise KeyError(f"{group} has no divider constant {constant}")
        found.append(model.constants[constant])
    return tuple(found)
