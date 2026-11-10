"""The allowed-failures rule of `gnc_analysis.error_bounds`."""

import pytest

from gnc_analysis.error_bounds import allowed_failures


@pytest.mark.parametrize(
    ("n", "p", "c", "expected"),
    [
        (852, 0.99, 0.90, 4),
        (852, 0.9973, 0.90, 0),
        (851, 0.9973, 0.90, None),
    ],
)
def test_allowed_failures_matches_the_known_values(
    n: int, p: float, c: float, expected: int | None
) -> None:
    """The rule reproduces the proposal's table, including the no-such-k case as None.

    Args:
        n: the run count.
        p: the reliability.
        c: the confidence.
        expected: the allowed failures, or None.
    """
    assert allowed_failures(n, p, c) == expected
