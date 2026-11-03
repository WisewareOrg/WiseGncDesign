"""One error metric summarized across runs."""

from dataclasses import dataclass

import numpy as np

from gnc_analysis.metric import Metric

__all__ = ["MetricSummary"]


@dataclass(frozen=True)
class MetricSummary:
    """One metric across the runs of a session.

    Attributes:
        metric: the metric summarized.
        errors: (n_runs, N), the metric for every run at every sample.
        final_mean, final_std, final_max: over runs, of each run's last sample, in
            `metric.unit`.
        growth_rate: slope of the ensemble RMS against time, in `metric.rate_unit`.
    """

    metric: Metric
    errors: np.ndarray
    final_mean: float
    final_std: float
    final_max: float
    growth_rate: float

    @property
    def final_3sigma(self) -> float:
        """Three times `final_std`, in `metric.unit`."""
        return 3.0 * self.final_std
