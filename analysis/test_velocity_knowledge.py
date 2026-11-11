"""Velocity knowledge: the worst velocity error over a run stays within x in a share p of runs.

Judges every SRS rung in the requirements tree that references this file, each with its own
x (m/s), p and c.
"""

from collections.abc import Callable

import numpy as np
import pytest
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults

from requirements_tree import limit, rungs
from runs import read_run


def velocity_error_m_s(v_truth_N: np.ndarray, v_est_N: np.ndarray) -> np.ndarray:
    """|v_truth - v_est| at each sample.

    Args:
        v_truth_N: (N, 3) m/s, inertial velocity in the inertial frame N.
        v_est_N: (N, 3) m/s, the estimate of the same.

    Returns:
        (N,) m/s.
    """
    return np.linalg.norm(v_truth_N - v_est_N, axis=-1)


@pytest.mark.parametrize("requirement_id", rungs(__file__))
def test_velocity_knowledge(
    requirement_id: str,
    claimed_runs: Callable[[str], dict[str, CaseResults]],
    verdict: Callable[..., None],
) -> None:
    """Find the worst velocity error of every claiming run, plot them, and judge the requirement.

    Args:
        requirement_id: the rung judged.
        claimed_runs: the results of the tests claiming an ID.
        verdict: judges the requirement from each run's number and saves the plots.
    """
    x = limit(requirement_id, "x")
    worst, figures = {}, {}
    for nodeid, results in claimed_runs(requirement_id).items():
        worst[nodeid] = {}
        for case, path in results.runs.items():
            run = read_run(path)
            error = velocity_error_m_s(run["truth/v_N"], run["est/v_BN_N"])
            worst[nodeid][case] = float(np.max(error))
        figure = Figure(layout="constrained")
        axes = figure.subplots()
        axes.hist(list(worst[nodeid].values()), bins=30)
        axes.axvline(x, color="k", linestyle="--", label="X")
        axes.set(
            xlabel="worst velocity error (m/s)",
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
