"""Attitude knowledge: the worst attitude error a run reports stays within x in a share p of runs.

Judges every SRS rung in the requirements tree that references this file, each with its own
x (degrees), p and c.
"""

from collections.abc import Callable

import numpy as np
import pytest
from matplotlib.figure import Figure
from scipy.spatial.transform import Rotation
from wise_dynamics.sessions import CaseResults

from harness.requirements_tree import limit, rungs
from harness.runs import at, read_run


def attitude_error_rad(q_truth_BN: np.ndarray, q_est_BN: np.ndarray) -> np.ndarray:
    """The principal angle between truth's attitude and the estimate's at each sample.

    Args:
        q_truth_BN: (N, 4) quaternion W X Y Z of the body frame B with respect to the inertial
            frame N.
        q_est_BN: (N, 4) the estimate of the same.

    Returns:
        (N,) rad, the magnitude of the rotation from the estimated attitude to the true one.
    """
    truth = Rotation.from_quat(q_truth_BN, scalar_first=True)
    estimate = Rotation.from_quat(q_est_BN, scalar_first=True)
    return (truth * estimate.inv()).magnitude()


@pytest.mark.parametrize("requirement_id", rungs(__file__))
def test_attitude_knowledge(
    requirement_id: str,
    claimed_runs: Callable[[str], dict[str, CaseResults]],
    verdict: Callable[..., None],
) -> None:
    """Find the worst attitude error of every claiming run, plot them, and judge the requirement.

    Each run's error is taken at every estimate nav wrote, against truth at the write's time.

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
            t = run["tlm_t/nav.bodyEciAttitude"]
            error = attitude_error_rad(at(run, "truth/q_BN", t), run["tlm/nav.bodyEciAttitude"])
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
