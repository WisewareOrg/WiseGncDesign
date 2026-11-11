"""Attitude knowledge: the worst attitude error over a run stays within x in a share p of runs.

Judges every SRS rung in the requirements tree that references this file, each with its own
x (degrees), p and c.
"""

from collections.abc import Callable

import numpy as np
import pytest
from matplotlib.figure import Figure
from scipy.spatial.transform import Rotation
from wise_dynamics.sessions import CaseResults

from requirements_tree import limit, rungs
from runs import read_run


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


@pytest.mark.parametrize("requirement_id", rungs(__file__))
def test_attitude_knowledge(
    requirement_id: str,
    claimed_runs: Callable[[str], dict[str, CaseResults]],
    verdict: Callable[..., None],
) -> None:
    """Find the worst attitude error of every claiming run, plot them, and judge the requirement.

    Args:
        requirement_id: the rung judged.
        claimed_runs: the results of the tests claiming an ID.
        verdict: judges the requirement from each run's number and saves the plots.
    """
    x = np.deg2rad(limit(requirement_id, "x"))
    worst, figures = {}, {}
    for nodeid, results in claimed_runs(requirement_id).items():
        worst[nodeid] = {}
        for case, path in results.runs.items():
            run = read_run(path)
            error = attitude_error_rad(run["truth/sigma_BN"], run["est/sigma_BN"])
            worst[nodeid][case] = float(np.max(error))
        figure = Figure(layout="constrained")
        axes = figure.subplots()
        axes.hist(list(worst[nodeid].values()), bins=30)
        axes.axvline(x, color="k", linestyle="--", label="X")
        axes.set(
            xlabel="worst attitude error (rad)",
            ylabel="runs",
            title=f"{requirement_id}: {nodeid.rsplit('::', 1)[-1]}",
        )
        axes.legend()
        figures[nodeid] = figure
    verdict(
        requirement_id,
        worst,
        figures,
        x=x,
        p=limit(requirement_id, "p"),
        c=limit(requirement_id, "c"),
    )
