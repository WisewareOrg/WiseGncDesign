"""SRS001, attitude knowledge: the worst attitude error stays within X in a share p of runs.

ID's limits X, p and c are read from its item in the Doorstop tree.
"""

from collections.abc import Callable

import numpy as np
from matplotlib.figure import Figure
from scipy.spatial.transform import Rotation
from wise_dynamics.sessions import CaseResults

from limits import limit
from runs import read_run

ID = "SRS001"
X = limit(ID, "x")  # rad
P = limit(ID, "p")
C = limit(ID, "c")


def attitude_error_rad(sigma_truth_BN: np.ndarray, sigma_est_BN: np.ndarray) -> np.ndarray:
    """The principal angle between truth's attitude and the estimate's at each sample.

    Args:
        sigma_truth_BN: (N, 3) MRP of the body frame B with respect to the inertial frame N.
        sigma_est_BN: (N, 3) the estimate of the same.

    Returns:
        (N,) rad, the magnitude of the rotation from the estimated attitude to the true one.
    """
    truth, estimate = Rotation.from_mrp(sigma_truth_BN), Rotation.from_mrp(sigma_est_BN)
    return (truth * estimate.inv()).magnitude()


def test_attitude_knowledge(
    claimed_runs: Callable[[str], dict[str, CaseResults]], verdict: Callable[..., None]
) -> None:
    """Find the worst attitude error of every claiming run, plot them, and judge the requirement.

    Args:
        claimed_runs: the results of the tests claiming an ID.
        verdict: judges the requirement from each run's number and saves the plots.
    """
    worst, figures = {}, {}
    for nodeid, results in claimed_runs(ID).items():
        worst[nodeid] = {}
        for case, path in results.runs.items():
            run = read_run(path)
            error = attitude_error_rad(run["truth/sigma_BN"], run["est/sigma_BN"])
            worst[nodeid][case] = float(np.max(error))
        figure = Figure(layout="constrained")
        axes = figure.subplots()
        axes.hist(list(worst[nodeid].values()), bins=30)
        axes.axvline(X, color="k", linestyle="--", label="X")
        axes.set(
            xlabel="worst attitude error (rad)",
            ylabel="runs",
            title=f"{ID}: {nodeid.rsplit('::', 1)[-1]}",
        )
        axes.legend()
        figures[nodeid] = figure
    verdict(ID, worst, figures, x=X, p=P, c=C)
