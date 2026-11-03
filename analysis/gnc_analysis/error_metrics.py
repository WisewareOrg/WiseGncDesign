"""Attitude, position and velocity error of a run against truth, and their summary across runs.

Each metric is computed per run and per sample:
- attitude error, deg: `4 atan(|sigma_truth ⊖ sigma_est|)`;
- position error, m: `|r_truth - r_est|`;
- velocity error, m/s: `|v_truth - v_est|`.
"""

from collections.abc import Sequence

import numpy as np

from gnc_analysis import mrp
from gnc_analysis.metric import Metric
from gnc_analysis.metric_summary import MetricSummary
from gnc_analysis.runs import Run
from gnc_analysis.summary import Summary

__all__ = [
    "METRICS",
    "attitude_error_deg",
    "growth_rate",
    "position_error_m",
    "summarize",
    "velocity_error_m_s",
]


def attitude_error_deg(run: Run) -> np.ndarray:
    """(N,) deg, the principal angle of `truth.sigma_BN ⊖ est.sigma_BN` at each sample."""
    return np.degrees(mrp.angle(mrp.subtract(run.truth.sigma_BN, run.est.sigma_BN)))


def position_error_m(run: Run) -> np.ndarray:
    """(N,) m, `|truth.r_N - est.r_N|` at each sample."""
    return np.linalg.norm(run.truth.r_N - run.est.r_N, axis=-1)


def velocity_error_m_s(run: Run) -> np.ndarray:
    """(N,) m/s, `|truth.v_N - est.v_N|` at each sample."""
    return np.linalg.norm(run.truth.v_N - run.est.v_N, axis=-1)


def growth_rate(t_s: np.ndarray, values: np.ndarray) -> float:
    """The slope of a least-squares line through `values` against `t_s`, in units of
    `values` per second."""
    slope, _ = np.polyfit(t_s, values, 1)
    return float(slope)


METRICS: tuple[Metric, ...] = (
    Metric("attitude error", "deg", "deg/s", attitude_error_deg, "attitude_error.png"),
    Metric("position error", "m", "m/s", position_error_m, "position_error.png"),
    Metric("velocity error", "m/s", "m/s^2", velocity_error_m_s, "velocity_error.png"),
)


def summarize(runs: Sequence[Run]) -> Summary:
    """Computes every metric in `METRICS` for every run in `runs`, which share `t_s` (as
    `load_run_directory` guarantees), and summarizes each across the ensemble."""
    t_s = runs[0].t_s
    summaries = []
    for metric in METRICS:
        errors = np.stack([metric.compute(run) for run in runs])
        final = errors[:, -1]
        rms = np.sqrt(np.mean(errors**2, axis=0))
        summaries.append(
            MetricSummary(
                metric=metric,
                errors=errors,
                final_mean=float(np.mean(final)),
                final_std=float(np.std(final)),
                final_max=float(np.max(final)),
                growth_rate=growth_rate(t_s, rms),
            )
        )
    return Summary(n_runs=len(runs), t_s=t_s, metrics=tuple(summaries))
