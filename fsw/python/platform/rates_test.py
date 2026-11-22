"""The Python build's rate-group driver counts base ticks as F´'s `Svc.RateGroupDriver` does."""

import pytest

from fsw.codegen.fpp_model import Model
from fsw.python.platform.rates import RateGroupDriver, dividers


def test_each_rate_group_runs_on_every_divider_th_tick_from_the_first():
    """The first tick runs every rate group; offsets are 0, as both builds configure them."""
    driver = RateGroupDriver((1, 2, 3))

    fired = [driver.tick() for _ in range(7)]

    assert fired == [[0, 1, 2], [0], [0, 1], [0, 2], [0, 1], [0], [0, 1, 2]]


def test_a_divider_of_zero_never_runs_its_rate_group_as_in_f_prime():
    """F´ skips a divisor of 0, and leaves it out of its tick count's rollover."""
    driver = RateGroupDriver((2, 0))

    assert [driver.tick() for _ in range(3)] == [[0], [], [0]]


def _constants(constants: dict[str, int | float]) -> Model:
    """A model holding only constants.

    Args:
        constants: each constant's value, by qualified name.

    Returns:
        The model.
    """
    return Model({}, {}, {}, constants, {}, {}, {})


def test_each_rate_group_takes_its_stem_s_divider_in_its_module():
    """`<stem>RateGroup` runs at `<stem>Divider`, in the rate groups' order."""
    model = _constants({"Mock.fastDivider": 1, "Mock.slowDivider": 2, "Other.fastDivider": 5})

    assert dividers(model, ("Mock.slowRateGroup", "Mock.fastRateGroup")) == (2, 1)


def test_a_rate_group_without_its_divider_constant_is_refused_naming_it():
    """A rate group whose module declares no `<stem>Divider` raises, naming the constant."""
    with pytest.raises(KeyError, match=r"Mock\.slowDivider"):
        dividers(_constants({"Mock.fastDivider": 1}), ("Mock.fastRateGroup", "Mock.slowRateGroup"))
