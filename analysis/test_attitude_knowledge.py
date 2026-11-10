"""SRS001, attitude knowledge: the worst attitude error stays within X in a share p of runs."""

from collections.abc import Callable
from pathlib import Path

import pytest
from matplotlib.figure import Figure
from wise_dynamics.sessions import CaseResults, session_directory

from gnc_analysis.error_bounds import allowed_failures, read_run, worst_attitude_error_rad

ID = "SRS001"  # placeholder
X = 1e-3  # placeholder, rad
P = 0.99  # placeholder
C = 0.90  # placeholder


def test_attitude_knowledge(
    request: pytest.FixtureRequest, claimed_runs: Callable[[str], dict[str, CaseResults]]
) -> None:
    """Judge each test that claims the requirement, then the requirement.

    Args:
        request: the pytest request.
        claimed_runs: the results of the tests claiming an ID.
    """
    rows = [
        "| Requirement | Test | Verdict | Failed/Found/Planned | Allowed |",
        "|---|---|---|---|---|",
    ]
    figure = Figure(layout="constrained")
    axes = figure.subplots()
    failing, unjudged = {}, []
    for nodeid, results in claimed_runs(ID).items():
        errors = {c: worst_attitude_error_rad(read_run(f)) for c, f in results.runs.items()}
        failed = [c for c in range(results.planned) if errors.get(c, 0) > X or c in results.crashes]
        found = sum(c in results.runs or c in results.crashes for c in range(results.planned))
        allowed = allowed_failures(results.planned, P, C)
        if found < results.planned or allowed is None:
            verdict = "not judged"
            unjudged.append(
                f"{nodeid}: {found} of {results.planned} cases found, allowed {allowed}"
            )
        elif len(failed) > allowed:
            verdict = "fail"
            failing[nodeid] = failed
        else:
            verdict = "pass"
        rows.append(
            f"| {ID} | {nodeid} | {verdict} | {len(failed)}/{found}/{results.planned} | {allowed} |"
        )
        axes.hist(list(errors.values()), bins=30, alpha=0.6, label=nodeid)
    axes.axvline(X, color="k", linestyle="--", label="X")
    axes.set(xlabel="worst attitude error (rad)", ylabel="runs", title=ID)
    axes.legend()
    report = Path(session_directory(request.config)) / "report"
    report.mkdir(exist_ok=True)
    figure.savefig(report / f"{ID}.png")
    (report / "matrix.md").write_text("\n".join(rows) + "\n")
    if failing:
        pytest.fail(f"{ID} failed cases: {failing}")
    if unjudged or len(rows) == 2:
        pytest.skip(f"{ID} not judged: {unjudged or 'no test claims it'}")
