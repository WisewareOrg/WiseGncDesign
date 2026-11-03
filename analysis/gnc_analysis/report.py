"""The error report of a set of runs: `summary.md` and one figure per metric."""

from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from gnc_analysis.error_metrics import summarize
from gnc_analysis.metric_summary import MetricSummary
from gnc_analysis.runs import load_run, load_run_directory
from gnc_analysis.summary import Summary

__all__ = ["analyze", "metric_figure", "write_report"]


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


def metric_figure(summary: Summary, s: MetricSummary) -> Figure:
    """One metric across its runs: every run drawn faintly, the ensemble mean and ±3σ in
    bold, against time in s."""
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
        metric_figure(summary, s).savefig(out_dir / s.metric.figure_name, dpi=150)


def analyze(path: Path, out_dir: Path) -> Summary:
    """Loads one run file, or every run file in a directory, summarizes them, writes the report
    into `out_dir`, and returns the summary.

    Raises:
        RunDataError: as `load_run` or `load_run_directory` does.
    """
    path = Path(path)
    runs = load_run_directory(path) if path.is_dir() else [load_run(path)]
    summary = summarize(runs)
    write_report(summary, out_dir)
    return summary
