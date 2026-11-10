"""SRS001, attitude knowledge: the worst attitude error stays within X in a share p of runs."""

import pytest
from matplotlib.figure import Figure
from wise_dynamics.sessions import read_test_results, recorded_tests, session_directory

from gnc_analysis.requirements import Cell, claimed_ids, judge_cell

ID = "SRS001"  # placeholder
X = 1e-3  # placeholder, rad
P = 0.99  # placeholder
C = 0.90  # placeholder


def write_report(report, cells: dict[str, Cell]) -> None:
    """Write the histogram of the worst errors and the matrix of cells.

    Args:
        report: the session's report directory.
        cells: each claiming test's cell by node ID.
    """
    report.mkdir(exist_ok=True)
    figure = Figure(layout="constrained")
    axes = figure.subplots()
    for nodeid, cell in cells.items():
        axes.hist(cell.errors, bins=30, alpha=0.6, label=nodeid)
    axes.axvline(X, color="k", linestyle="--", label="X")
    axes.set(xlabel="worst attitude error (rad)", ylabel="runs", title=ID)
    axes.legend()
    figure.savefig(report / f"{ID}.png")
    rows = [
        "| Requirement | Test | Verdict | Failed/Found/Planned | Allowed |",
        "|---|---|---|---|---|",
    ]
    rows += [
        f"| {ID} | {nodeid} | {c.verdict} | {len(c.failed)}/{c.found}/{c.planned} | {c.allowed} |"
        for nodeid, c in cells.items()
    ]
    (report / "matrix.md").write_text("\n".join(rows) + "\n")


def test_attitude_knowledge(request: pytest.FixtureRequest) -> None:
    """Judge the active session's tests that claim the requirement.

    Args:
        request: the pytest request.
    """
    session = session_directory(request.config)
    cells = {
        t.nodeid: judge_cell(read_test_results(t.directory), X, P, C)
        for t in recorded_tests(session)
        if ID in claimed_ids(request.config.rootpath, t.nodeid)
    }
    write_report(session / "report", cells)
    failing = {n: c.failed for n, c in cells.items() if c.verdict == "fail"}
    if failing:
        pytest.fail(f"{ID} failed cases: {failing}")
    unjudged = [f"{n}: {c.reason}" for n, c in cells.items() if c.verdict == "not judged"]
    if unjudged or not cells:
        pytest.skip(f"{ID} not judged: {unjudged or 'no test claims it'}")
