"""Wheel momentum: the wheel's spin-axis momentum stays within x of the commanded torque's integral.

Judges every SRS rung in the requirements tree that references this file, each with its own
x (N*m*s), p and c.
"""

from collections.abc import Callable

import numpy as np
import pytest
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults

from harness.requirements_tree import limit, rungs
from harness.runs import read_run


def wheel_momentum_error_N_m_s(
    t_s: np.ndarray, H: np.ndarray, t_written_s: np.ndarray, torque_N_m: np.ndarray
) -> np.ndarray:
    """|H - (H0 + integral of the commanded torque)| at each sample.

    A torque written at t_k acts from t_k until the next write, and none acts before the first, so
    the integral up to t is the sum of each torque over the part of its interval before t.

    Args:
        t_s: (N,) s, the sample times, the first of which is H0's.
        H: (N,) N*m*s, the wheel's spin-axis momentum at each sample.
        t_written_s: (M,) s, each torque write's time, increasing.
        torque_N_m: (M,) N*m, the torque each write commanded.

    Returns:
        (N,) N*m*s.
    """
    impulse_at_write = np.concatenate(([0.0], np.cumsum(torque_N_m[:-1] * np.diff(t_written_s))))
    acting = np.searchsorted(t_written_s, t_s, side="right") - 1
    k = np.maximum(acting, 0)
    impulse = np.where(
        acting >= 0, impulse_at_write[k] + torque_N_m[k] * (t_s - t_written_s[k]), 0.0
    )
    return np.abs(H - (H[0] + impulse))


@pytest.mark.parametrize("requirement_id", rungs(__file__))
def test_wheel_momentum(
    requirement_id: str,
    claimed_runs: Callable[[str], dict[str, CaseResults]],
    verdict: Callable[..., None],
) -> None:
    """Find the worst wheel momentum error of every claiming run, plot them, and judge the rung.

    Each run's error is taken at every dynamics step, against the torque the spinner wrote.

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
            error = wheel_momentum_error_N_m_s(
                run["t_s"],
                run["truth/wheel_momentum"],
                run["tlm_t/spinner.wheelTorque"],
                run["tlm/spinner.wheelTorque"],
            )
            worst[nodeid][case] = float(np.max(error))
        figure = Figure(layout="constrained")
        axes = figure.subplots()
        axes.hist(list(worst[nodeid].values()), bins=30)
        axes.axvline(x, color="k", linestyle="--", label="X")
        axes.set(
            xlabel="worst wheel momentum error (N*m*s)",
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
