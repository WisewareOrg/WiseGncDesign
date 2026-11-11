"""SRS002, velocity knowledge: the worst velocity error stays within X in a share p of runs.

ID's limits X, p and c are read from its item in the Doorstop tree.
"""

from collections.abc import Callable

import numpy as np
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults

from limits import limit
from runs import read_run

ID = "SRS002"
X = limit(ID, "x")  # m/s
P = limit(ID, "p")
C = limit(ID, "c")


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
        verdict: judges the requirement from each run's number and saves the plots.
    """
    worst, figures = {}, {}
    for nodeid, results in claimed_runs(ID).items():
        worst[nodeid] = {}
        for case, path in results.runs.items():
            run = read_run(path)
            error = velocity_error_m_s(run["truth/v_N"], run["est/v_BN_N"])
            worst[nodeid][case] = float(np.max(error))
        figure = Figure(layout="constrained")
        axes = figure.subplots()
        axes.hist(list(worst[nodeid].values()), bins=30)
        axes.axvline(X, color="k", linestyle="--", label="X")
        axes.set(
            xlabel="worst velocity error (m/s)",
            ylabel="runs",
            title=f"{ID}: {nodeid.rsplit('::', 1)[-1]}",
        )
        axes.legend()
        figures[nodeid] = figure
    verdict(ID, worst, figures, x=X, p=P, c=C)
