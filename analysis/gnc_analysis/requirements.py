"""Requirement analysis: how many failed runs a requirement allows, and the metrics it judges.

A run is one run file as `error_bounds.read_run` returns it.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
from scipy.stats import beta

from gnc_analysis.error_bounds import attitude_error_rad

__all__ = ["Requirement", "allowed_failures", "worst_attitude_error_rad"]


@dataclass(frozen=True)
class Requirement:
    """A requirement a Monte Carlo session is judged against.

    A run passes when `metric(run)` is at most `threshold`.

    Attributes:
        id: the requirement's identifier, which `verifies` marks name.
        statement: the requirement's text.
        threshold: `X`, the largest metric value a passing run may have.
        p: the reliability the requirement demands, the share of runs that pass.
        c: the confidence the demonstration demands.
        metric: maps one run to the scalar compared with `threshold`.
    """

    id: str
    statement: str
    threshold: float
    p: float
    c: float
    metric: Callable[[Mapping[str, np.ndarray]], float]


def allowed_failures(n: int, p: float, c: float) -> int | None:
    """The most failed runs out of `n` that still show reliability `p` at confidence `c`.

    The failure rate's one-sided Clopper-Pearson upper bound at confidence `c` must stay within
    `1 - p`.

    Args:
        n: the number of runs.
        p: the reliability the requirement demands, the share of runs that pass.
        c: the confidence the demonstration demands.

    Returns:
        The largest failure count `k` whose upper bound is within `1 - p`, or None when even zero
        failures cannot show `p` at `c` with `n` runs.
    """
    k = 0
    while k < n and beta.ppf(c, k + 1, n - k) <= 1.0 - p:
        k += 1
    return k - 1 if k > 0 else None


def worst_attitude_error_rad(run: Mapping[str, np.ndarray]) -> float:
    """The largest attitude error of the estimate against truth over a run.

    Args:
        run: one run, holding `truth/sigma_BN` and `est/sigma_BN`.

    Returns:
        The largest error over the samples, in rad.
    """
    return float(np.max(attitude_error_rad(run["truth/sigma_BN"], run["est/sigma_BN"])))
