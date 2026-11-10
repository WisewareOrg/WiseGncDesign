"""SRS002, velocity knowledge: the worst velocity error stays within X in a share p of runs."""

from collections.abc import Callable

import numpy as np
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults

from runs import read_run

ID = "SRS002"  # placeholder
X = 5  # placeholder, m/s
P = 0.99  # placeholder
C = 0.90  # placeholder


def velocity_error_m_s(v_truth_N: np.ndarray, v_est_N: np.ndarray) -> np.ndarray:
    """|v_truth - v_est| at each sample.

    Args:
        v_truth_N: (N, 3) m/s, inertial velocity in the inertial frame N.
        v_est_N: (N, 3) m/s, the estimate of the same.

    Returns:
        (N,) m/s.
    """
    return np.linalg.norm(v_truth_N - v_est_N, axis=-1)


def test_velocity_knowledge(
    claimed_runs: Callable[[str], dict[str, CaseResults]], verdict: Callable[..., None]
) -> None:
    """Find the worst velocity error of every claiming run, plot them, and judge the requirement.

    Args:
        claimed_runs: the results of the tests claiming an ID.
        verdict: judges the requirement from each run's number.
    """
    figure = Figure(layout="constrained")
    axes = figure.subplots()
    worst = {}
    for nodeid, results in claimed_runs(ID).items():
        worst[nodeid] = {}
        for case, path in results.runs.items():
            run = read_run(path)
            error = velocity_error_m_s(run["truth/v_N"], run["est/v_BN_N"])
            worst[nodeid][case] = float(np.max(error))
        axes.hist(list(worst[nodeid].values()), bins=30, alpha=0.6, label=nodeid)
    axes.axvline(X, color="k", linestyle="--", label="X")
    axes.set(xlabel="worst velocity error (m/s)", ylabel="runs", title=ID)
    axes.legend()
    verdict(ID, worst, X, P, C, figure)
