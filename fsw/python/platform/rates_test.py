"""The Python build's rate-group driver counts base ticks as F´'s `Svc.RateGroupDriver` does."""

from fsw.python.platform.rates import RateGroupDriver


def test_each_rate_group_runs_on_every_divider_th_tick_from_the_first():
    """The first tick runs every rate group; offsets are 0, as both builds configure them."""
    driver = RateGroupDriver((1, 2, 3))

    fired = [driver.tick() for _ in range(7)]

    assert fired == [[0, 1, 2], [0], [0, 1], [0, 2], [0, 1], [0], [0, 1, 2]]


def test_a_divider_of_zero_never_runs_its_rate_group_as_in_f_prime():
    """F´ skips a divisor of 0, and leaves it out of its tick count's rollover."""
    driver = RateGroupDriver((2, 0))

    assert [driver.tick() for _ in range(3)] == [[0], [], [0]]
