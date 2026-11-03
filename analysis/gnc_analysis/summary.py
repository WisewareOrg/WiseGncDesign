"""Every error metric summarized across runs."""

from dataclasses import dataclass

import numpy as np

from gnc_analysis.metric_summary import MetricSummary

__all__ = ["Summary"]


@dataclass(frozen=True)
class Summary:
    """Every metric across runs sharing `t_s`.

    Attributes:
        n_runs: how many runs were summarized.
        t_s: (N,) s, the shared sample times.
        metrics: one `MetricSummary` per entry of `METRICS`, in that order.
    """

    n_runs: int
    t_s: np.ndarray
    metrics: tuple[MetricSummary, ...]

    @property
    def duration_s(self) -> float:
        """Span of `t_s`, in s."""
        return float(self.t_s[-1] - self.t_s[0])
