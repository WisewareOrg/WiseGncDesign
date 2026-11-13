"""Position knowledge: the worst position error a run reports stays within x in a share p of runs.

Judges every SRS rung in the requirements tree that references this file, each with its own
x (m), p and c.
"""

from collections.abc import Callable

import numpy as np
import pytest
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults

from harness.requirements_tree import limit, rungs
from harness.runs import at, read_run


def position_error_m(r_truth_N: np.ndarray, r_est_N: np.ndarray) -> np.ndarray:
    """|r_truth - r_est| at each sample.

    Args:
        r_truth_N: (N, 3) m, inertial position in the inertial frame N.
        r_est_N: (N, 3) m, the estimate of the same.

    Returns:
        (N,) m.
    """
    return np.linalg.norm(r_truth_N - r_est_N, axis=-1)


@pytest.mark.parametrize("requirement_id", rungs(__file__))
def test_position_knowledge(
    requirement_id: str,
    claimed_runs: Callable[[str], dict[str, CaseResults]],
    verdict: Callable[..., None],
) -> None:
    """Find the worst position error of every claiming run, plot them, and judge the requirement.

    Each run's error is taken at every estimate nav wrote, against truth at the write's time.

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
            t = run["tlm_t/nav.bodyEciPos"]
            error = position_error_m(at(run, "truth/r_N", t), run["tlm/nav.bodyEciPos"])
            worst[nodeid][case] = float(np.max(error))
        figure = Figure(layout="constrained")
        axes = figure.subplots()
        axes.hist(list(worst[nodeid].values()), bins=30)
        axes.axvline(x, color="k", linestyle="--", label="X")
        axes.set(
            xlabel="worst position error (m)",
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
