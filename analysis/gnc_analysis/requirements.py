"""Requirement analysis: how many failed runs a requirement allows, and the metrics it judges.

A run is one run file as `error_bounds.read_run` returns it.
"""

from collections.abc import Mapping

import numpy as np
from scipy.stats import beta

from gnc_analysis.error_bounds import attitude_error_rad

__all__ = ["allowed_failures", "worst_attitude_error_rad"]


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
