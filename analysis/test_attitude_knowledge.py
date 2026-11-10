"""SRS001, attitude knowledge: judges the estimate's worst attitude error."""

from typing import Any

import numpy as np
from matplotlib.figure import Figure

from gnc_analysis.requirements import Requirement, worst_attitude_error_rad

REQUIREMENT = Requirement(
    id="SRS001",  # placeholder
    statement="Attitude knowledge error shall stay <= X over the run.",
    threshold=1e-3,  # placeholder X, rad
    p=0.99,  # placeholder
    c=0.90,  # placeholder
    metric=worst_attitude_error_rad,
)


def plot_worst_attitude_error(
    values: dict[str, dict[int, float]], requirement: Requirement
) -> Figure:
    """Histogram the worst attitude error of each run, with the threshold marked.

    Args:
        values: each claiming test's metric by case number.
        requirement: the requirement being judged.

    Returns:
        The figure.
    """
    figure = Figure(layout="constrained")
    axes = figure.subplots()
    for test, by_case in values.items():
        axes.hist(np.fromiter(by_case.values(), float), bins=30, alpha=0.6, label=test)
    axes.axvline(requirement.threshold, color="k", linestyle="--", label="X")
    axes.set(xlabel="worst attitude error (rad)", ylabel="runs", title=requirement.id)
    axes.legend()
    return figure


def test_attitude_knowledge(session_run: Any) -> None:
    """Judge one case of a claiming test.

    Args:
        session_run: the case under test.
    """
    session_run.check()


def test_attitude_knowledge_verdict(requirement_verdict: Any) -> None:
    """Judge the requirement across its claiming tests and plot the metrics.

    Args:
        requirement_verdict: the requirement under test.
    """
    requirement_verdict.plot(plot_worst_attitude_error)
    requirement_verdict.check()
