"""SRS003, position knowledge: the worst position error stays within X in a share p of runs."""

from collections.abc import Callable

import numpy as np
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults

from runs import read_run

ID = "SRS003"  # placeholder
X = 5000  # placeholder, m
P = 0.99  # placeholder
C = 0.90  # placeholder


def position_error_m(r_truth_N: np.ndarray, r_est_N: np.ndarray) -> np.ndarray:
    """|r_truth - r_est| at each sample.

    Args:
        r_truth_N: (N, 3) m, inertial position in the inertial frame N.
        r_est_N: (N, 3) m, the estimate of the same.

    Returns:
        (N,) m.
    """
    return np.linalg.norm(r_truth_N - r_est_N, axis=-1)


def test_position_knowledge(
    claimed_runs: Callable[[str], dict[str, CaseResults]], verdict: Callable[..., None]
) -> None:
    """Find the worst position error of every claiming run, plot them, and judge the requirement.

    Args:
        claimed_runs: the results of the tests claiming an ID.
        verdict: judges the requirement from each run's number and saves the plots.
    """
    worst, figures = {}, {}
    for nodeid, results in claimed_runs(ID).items():
        worst[nodeid] = {}
        for case, path in results.runs.items():
            run = read_run(path)
            error = position_error_m(run["truth/r_N"], run["est/r_BN_N"])
            worst[nodeid][case] = float(np.max(error))
        figure = Figure(layout="constrained")
        axes = figure.subplots()
        axes.hist(list(worst[nodeid].values()), bins=30)
        axes.axvline(X, color="k", linestyle="--", label="X")
        axes.set(
            xlabel="worst position error (m)",
            ylabel="runs",
            title=f"{ID}: {nodeid.rsplit('::', 1)[-1]}",
        )
        axes.legend()
        figures[nodeid] = figure
    verdict(ID, worst, X, P, C, figures)
