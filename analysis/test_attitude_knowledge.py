"""SRS001, attitude knowledge: the worst attitude error stays within X in a share p of runs."""

from collections.abc import Callable

import numpy as np
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults

from gnc_analysis.error_bounds import attitude_error_rad, read_run

ID = "SRS001"  # placeholder
X = 1  # placeholder, rad
P = 0.99  # placeholder
C = 0.90  # placeholder


def test_attitude_knowledge(
    claimed_runs: Callable[[str], dict[str, CaseResults]], verdict: Callable[..., None]
) -> None:
    """Find the worst attitude error of every claiming run, plot them, and judge the requirement.

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
            error = attitude_error_rad(run["truth/sigma_BN"], run["est/sigma_BN"])
            worst[nodeid][case] = float(np.max(error))
        axes.hist(list(worst[nodeid].values()), bins=30, alpha=0.6, label=nodeid)
    axes.axvline(X, color="k", linestyle="--", label="X")
    axes.set(xlabel="worst attitude error (rad)", ylabel="runs", title=ID)
    axes.legend()
    verdict(ID, worst, X, P, C, figure)
