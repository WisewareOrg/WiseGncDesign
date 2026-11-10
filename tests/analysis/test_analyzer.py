"""The attitude-knowledge requirement test: cells, verdicts and the evidence it writes.

The fake requirement keeps the real test's code with p = 0.8, c = 0.5, X = 1e-3 rad. Of 10 planned
cases that allows one failure, as `allowed_failures(10, 0.8, 0.5)` gives.
"""

import json
from pathlib import Path

import h5py
import numpy as np
import pytest
from wise_dynamics.sessions import (
    CaseResults,
    crash_path,
    read_test_results,
    run_path,
    write_planned,
)

from gnc_analysis.requirements import judge_cell

REPO = Path(__file__).resolve().parents[2]
GOOD_RAD = 0.9e-3
BAD_RAD = 1.5e-3
PLANNED = 10
MC = """\
import pytest


@pytest.mark.verifies("SRS001")
def test_tagged():
    pass


def test_untagged():
    pass
"""
SIM_TEST = """\
import numpy as np
import pytest


@pytest.mark.verifies("SRS001")
@pytest.mark.sim_runs(4)
@pytest.mark.sim_duration_s(3)
def test_tagged(sim_run_file):
    est = np.zeros((5, 3))
    est[2, 2] = np.tan(0.9e-3 / 4.0)
    sim_run_file(
        {
            "t_s": (np.linspace(0.0, 1.0, 5), "s"),
            "truth/sigma_BN": (np.zeros((5, 3)), "-"),
            "est/sigma_BN": (est, "-"),
        }
    )
"""


def write_run(path: Path, error_rad: float) -> None:
    """Write a run file whose worst attitude error is `error_rad`.

    Args:
        path: the run file to create.
        error_rad: the rotation error of the estimate at one sample, in rad.
    """
    est = np.zeros((5, 3))
    est[2, 2] = np.tan(error_rad / 4.0)
    with h5py.File(path, "w") as f:
        f["t_s"] = np.linspace(0.0, 1.0, 5)
        f["truth/sigma_BN"] = np.zeros((5, 3))
        f["est/sigma_BN"] = est


def write_cases(
    directory: Path,
    bad: tuple[int, ...] = (),
    crashed: tuple[int, ...] = (),
    missing: tuple[int, ...] = (),
    test: str = "test_tagged",
) -> CaseResults:
    """Write a test's session folder.

    Args:
        directory: the test's folder in a session.
        bad: cases whose run exceeds the threshold.
        crashed: cases with a crash record and no run file.
        missing: cases with neither file.
        test: the function the folder records.

    Returns:
        What `read_test_results` reads from it.
    """
    write_planned(directory, PLANNED, f"tests/test_mc.py::{test}")
    for case in range(PLANNED):
        if case in missing:
            continue
        if case in crashed:
            crash_path(directory, case).write_text(json.dumps({"exception": "boom"}))
        else:
            write_run(run_path(directory, case), BAD_RAD if case in bad else GOOD_RAD)
    return read_test_results(directory)


@pytest.fixture
def project(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A project holding the requirement test with p = 0.8, c = 0.5 and an empty session.

    Args:
        pytester: the pytester fixture.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The pytester, rooted in the project.
    """
    source = (REPO / "analysis" / "test_attitude_knowledge.py").read_text()
    source = source.replace("P = 0.99", "P = 0.8").replace("C = 0.90", "C = 0.5")
    assert "P = 0.8 " in source and "C = 0.5 " in source
    pytester.makefile(".ini", pytest="[pytest]\nmarkers =\n    verifies(*ids): a claim\n")
    pytester.makepyfile(**{"analysis/test_attitude_knowledge": source, "tests/test_mc": MC})
    (pytester.path / "monte_carlo").mkdir()
    (pytester.path / "monte_carlo" / "SESSION").write_text("s1\n")
    monkeypatch.setenv("COLUMNS", "400")
    return pytester


def judge(project: pytest.Pytester) -> pytest.RunResult:
    """Run the requirement test in a subprocess.

    Args:
        project: the project.

    Returns:
        The result.
    """
    return project.runpytest_subprocess("analysis", "-rs", "-p", "no:xdist")


def test_failures_within_the_allowance_pass(tmp_path: Path) -> None:
    """One failure of ten is allowed and the cell passes.

    Args:
        tmp_path: a scratch folder.
    """
    cell = judge_cell(write_cases(tmp_path, bad=(3,)), 1e-3, 0.8, 0.5)

    assert (cell.verdict, cell.failed, cell.allowed) == ("pass", [3], 1)


def test_a_crash_counts_as_a_failed_case(tmp_path: Path) -> None:
    """A crash and a bad run make two failures, over the allowance of one.

    Args:
        tmp_path: a scratch folder.
    """
    cell = judge_cell(write_cases(tmp_path, bad=(3,), crashed=(5,)), 1e-3, 0.8, 0.5)

    assert (cell.verdict, cell.failed) == ("fail", [3, 5])


def test_failures_over_the_allowance_fail_and_name_the_cases(project: pytest.Pytester) -> None:
    """The requirement fails, lists the failing case numbers and the matrix records the cell.

    Args:
        project: the project.
    """
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged"
    write_cases(directory, bad=(2, 7))

    result = judge(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*SRS001 failed cases: *[[]2, 7[]]*"])
    matrix = (project.path / "monte_carlo" / "s1" / "report" / "matrix.md").read_text()
    assert "| SRS001 | tests/test_mc.py::test_tagged | fail | 2/10/10 | 1 |" in matrix


def test_a_missing_case_leaves_the_requirement_not_judged(project: pytest.Pytester) -> None:
    """A case with neither run nor crash skips the requirement and says so.

    Args:
        project: the project.
    """
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged"
    write_cases(directory, bad=(2, 7), missing=(4,))

    result = judge(project)

    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*test_tagged: 1 of 10 cases have no result*"])


def test_an_untagged_test_is_not_judged(project: pytest.Pytester) -> None:
    """A test without the mark is no cell, so nothing claims the requirement.

    Args:
        project: the project.
    """
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_untagged"
    write_cases(directory, bad=(2, 7), test="test_untagged")

    result = judge(project)

    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*no test claims it*"])
    assert "test_untagged" not in (directory.parents[1] / "report" / "matrix.md").read_text()


def test_a_session_written_by_the_wise_dynamics_plugin_passes(project: pytest.Pytester) -> None:
    """A real `sim_` test's session is found and judged, and the evidence is written.

    Four planned cases are the fewest that can show p = 0.8 at c = 0.5.

    Args:
        project: the project.
    """
    (project.path / "tests" / "test_mc.py").write_text(SIM_TEST)
    out = ("-o", "sim_out=monte_carlo")
    project.runpytest_subprocess("--sim-session", "s1", *out)
    project.runpytest_subprocess("tests/test_mc.py", *out, "-n", "0").assert_outcomes(passed=4)

    judge(project).assert_outcomes(passed=1)

    report = project.path / "monte_carlo" / "s1" / "report"
    assert (report / "SRS001.png").read_bytes().startswith(b"\x89PNG")
    assert "| pass | 0/4/4 | 0 |" in (report / "matrix.md").read_text()
