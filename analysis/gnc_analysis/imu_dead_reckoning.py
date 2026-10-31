"""Attitude, position and velocity error analysis over recorded runs (see runs.py for what a
run file must contain).

For every run: attitude error e(t) = 4*atan|sigma_truth (-) sigma_est| in degrees, position error
|r_truth - r_est| in m, velocity error |v_truth - v_est| in m/s. Across the ensemble: a summary
and a plot per metric. Independent of WiseGncDesign and Basilisk; see mrp.py for the local MRP
math.
"""

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from gnc_analysis import mrp  # noqa: E402
from gnc_analysis.runs import Run, load_campaign, load_run  # noqa: E402


def attitude_error_deg(run: Run) -> np.ndarray:
    """Per-sample attitude error angle, in degrees, for one run."""
    err = mrp.subtract(run.truth_sigma_BN, run.est_sigma_BN)
    over_one = np.linalg.norm(err, axis=-1) > 1.0
    err[over_one] = mrp.shadow(err[over_one])

    return np.degrees(mrp.angle(err))


def _vector_error(truth: np.ndarray, est: np.ndarray) -> np.ndarray:
    return np.linalg.norm(truth - est, axis=-1)


def position_error_m(run: Run) -> np.ndarray:
    """Per-sample position error magnitude, in m, for one run."""
    return _vector_error(run.truth_r_N, run.est_r_N)


def velocity_error_m_s(run: Run) -> np.ndarray:
    """Per-sample velocity error magnitude, in m/s, for one run."""
    return _vector_error(run.truth_v_N, run.est_v_N)


def growth_rate(t_s: np.ndarray, rms: np.ndarray) -> float:
    """Slope of a linear fit of ensemble RMS error vs time."""
    slope, _ = np.polyfit(t_s, rms, 1)
    return float(slope)


@dataclass(frozen=True)
class Metric:
    label: str
    unit: str
    rate_unit: str
    compute: Callable[[Run], np.ndarray]
    figure_name: str


METRICS = [
    Metric("attitude error", "deg", "deg/s", attitude_error_deg, "attitude_error.png"),
    Metric("position error", "m", "m/s", position_error_m, "position_error.png"),
    Metric("velocity error", "m/s", "m/s^2", velocity_error_m_s, "velocity_error.png"),
]


def _plot_metric(
    out_dir: Path,
    metric: Metric,
    t_s: np.ndarray,
    errors: np.ndarray,
    mean_t: np.ndarray,
    std_t: np.ndarray,
    n_runs: int,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for e in errors:
        ax.plot(t_s, e, color="0.75", linewidth=0.5)
    ax.plot(t_s, mean_t, color="C0", linewidth=2, label="ensemble mean")
    ax.plot(t_s, mean_t + 3 * std_t, color="C0", linewidth=1.5, linestyle="--", label="±3σ")
    ax.plot(t_s, mean_t - 3 * std_t, color="C0", linewidth=1.5, linestyle="--")
    ax.set_xlabel("t [s]")
    ax.set_ylabel(f"{metric.label} [{metric.unit}]")
    ax.set_title(f"{metric.label.capitalize()}, {n_runs} run(s)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / metric.figure_name, dpi=150)
    plt.close(fig)


def _load_runs(path: Path) -> list[Run]:
    """Load one run (path is a .h5 file) or an ensemble (path is a directory of run_*.h5)."""
    path = Path(path)
    if path.is_dir():
        return load_campaign(path)
    return [load_run(path)]


def analyze(path: Path, out_dir: Path) -> None:
    """Load the run or campaign at path, score attitude/position/velocity error, and write
    summary.md and one figure per metric into out_dir."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = _load_runs(path)
    t_s = runs[0].t_s
    duration_s = float(t_s[-1] - t_s[0])

    summary_lines = [
        "# Attitude, position and velocity error summary",
        "",
        f"- Runs: {len(runs)}",
        f"- Duration: {duration_s:.1f} s",
    ]

    for metric in METRICS:
        errors = np.stack([metric.compute(r) for r in runs], axis=0)  # (n_runs, n_steps)
        mean_t = np.mean(errors, axis=0)
        std_t = np.std(errors, axis=0)
        rms_t = np.sqrt(np.mean(errors**2, axis=0))

        final = errors[:, -1]
        final_mean = float(np.mean(final))
        final_std = float(np.std(final))
        final_max = float(np.max(final))
        rate = growth_rate(t_s, rms_t)

        summary_lines += [
            "",
            f"## {metric.label.capitalize()}",
            f"- Final mean: {final_mean:.4f} {metric.unit}",
            f"- Final std: {final_std:.4f} {metric.unit}",
            f"- Final 3-sigma: {3 * final_std:.4f} {metric.unit}",
            f"- Final max: {final_max:.4f} {metric.unit}",
            f"- Growth rate (linear fit of ensemble RMS vs time): {rate:.6f} {metric.rate_unit}",
        ]

        _plot_metric(out_dir, metric, t_s, errors, mean_t, std_t, len(runs))

    (out_dir / "summary.md").write_text("\n".join(summary_lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze one run or a directory of runs for attitude, position and "
        "velocity error."
    )
    parser.add_argument("path", type=Path, help="a run_<NNNN>.h5 file, or a directory of them")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.path, args.out)


if __name__ == "__main__":
    main()
