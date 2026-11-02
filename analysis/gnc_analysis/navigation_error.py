"""Attitude, position and velocity error of recorded runs against truth, per run and across a
campaign, written as a Markdown summary and one figure per metric.

Metrics, per run and per sample:
- attitude error, deg: `4 atan(|sigma_truth ⊖ sigma_est|)`;
- position error, m: `|r_truth - r_est|`;
- velocity error, m/s: `|v_truth - v_est|`.

`gnc-analyze <run.h5 | campaign_dir> --out <dir>` runs `analyze` from the command line.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from gnc_analysis import mrp
from gnc_analysis.runs import Run, RunDataError, load_campaign, load_run

__all__ = [
    "METRICS",
    "Metric",
    "MetricSummary",
    "Summary",
    "analyze",
    "attitude_error_deg",
    "growth_rate",
    "load_runs",
    "main",
    "position_error_m",
    "summarize",
    "velocity_error_m_s",
    "write_report",
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


@dataclass(frozen=True)
class Metric:
    """One error metric: its name, units, per-run computation and figure file name."""

    label: str
    unit: str
    rate_unit: str
    compute: Callable[[Run], np.ndarray]
    figure_name: str


METRICS: tuple[Metric, ...] = (
    Metric("attitude error", "deg", "deg/s", attitude_error_deg, "attitude_error.png"),
    Metric("position error", "m", "m/s", position_error_m, "position_error.png"),
    Metric("velocity error", "m/s", "m/s^2", velocity_error_m_s, "velocity_error.png"),
)


@dataclass(frozen=True)
class MetricSummary:
    """One metric across a campaign.

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


@dataclass(frozen=True)
class Summary:
    """Every metric across a campaign of runs sharing `t_s`.

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


def summarize(runs: Sequence[Run]) -> Summary:
    """Computes every metric in `METRICS` for every run in `runs`, which share `t_s` (as
    `load_campaign` guarantees), and summarizes each across the ensemble."""
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


def _summary_markdown(summary: Summary) -> str:
    lines = [
        "# Attitude, position and velocity error summary",
        "",
        f"- Runs: {summary.n_runs}",
        f"- Duration: {summary.duration_s:.1f} s",
    ]
    for s in summary.metrics:
        unit, rate_unit = s.metric.unit, s.metric.rate_unit
        lines += [
            "",
            f"## {s.metric.label.capitalize()}",
            f"- Final mean: {s.final_mean:.4f} {unit}",
            f"- Final std: {s.final_std:.4f} {unit}",
            f"- Final 3-sigma: {s.final_3sigma:.4f} {unit}",
            f"- Final max: {s.final_max:.4f} {unit}",
            f"- Growth rate (linear fit of ensemble RMS vs time): {s.growth_rate:.6f} {rate_unit}",
        ]
    return "\n".join(lines) + "\n"


def _metric_figure(summary: Summary, s: MetricSummary) -> Figure:
    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()
    t_s = summary.t_s
    mean = np.mean(s.errors, axis=0)
    std = np.std(s.errors, axis=0)
    for errors in s.errors:
        ax.plot(t_s, errors, color="0.75", linewidth=0.5)
    ax.plot(t_s, mean, color="C0", linewidth=2, label="ensemble mean")
    ax.plot(t_s, mean + 3 * std, color="C0", linewidth=1.5, linestyle="--", label="±3σ")
    ax.plot(t_s, mean - 3 * std, color="C0", linewidth=1.5, linestyle="--")
    ax.set_xlabel("t [s]")
    ax.set_ylabel(f"{s.metric.label} [{s.metric.unit}]")
    ax.set_title(f"{s.metric.label.capitalize()}, {summary.n_runs} run(s)")
    ax.legend()
    fig.tight_layout()
    return fig


def write_report(summary: Summary, out_dir: Path) -> None:
    """Writes `summary.md` and one figure per metric (`Metric.figure_name`, PNG) into
    `out_dir`, creating it if needed. Each figure draws every run faintly and the ensemble
    mean and ±3σ in bold."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text(_summary_markdown(summary))
    for s in summary.metrics:
        _metric_figure(summary, s).savefig(out_dir / s.metric.figure_name, dpi=150)


def load_runs(path: Path) -> list[Run]:
    """Loads one run when `path` is a file, or a campaign when it is a directory.

    Raises:
        RunDataError: as `load_run` or `load_campaign` does.
    """
    path = Path(path)
    return load_campaign(path) if path.is_dir() else [load_run(path)]


def analyze(path: Path, out_dir: Path) -> Summary:
    """Loads the run or campaign at `path`, summarizes it, writes the report into `out_dir`,
    and returns the summary.

    Raises:
        RunDataError: as `load_runs` does.
    """
    summary = summarize(load_runs(path))
    write_report(summary, out_dir)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """The `gnc-analyze` command. Returns 0 on success and 1 when the input is rejected by
    the loader, printing the loader's message to stderr; argparse exits with 2 on a usage
    error."""
    parser = argparse.ArgumentParser(
        prog="gnc-analyze",
        description="Attitude, position and velocity error of one run file or a directory of "
        "them, against truth.",
    )
    parser.add_argument("path", type=Path, help="a run_<NNNN>.h5 file, or a directory of them")
    parser.add_argument("--out", type=Path, required=True, help="directory for the report")
    args = parser.parse_args(argv)
    try:
        analyze(args.path, args.out)
    except RunDataError as exc:
        print(f"gnc-analyze: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
