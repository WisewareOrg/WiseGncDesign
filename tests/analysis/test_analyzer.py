"""The attitude-knowledge requirement test: cells, verdicts and the evidence it writes.

The fake requirement keeps the real test's code with p = 0.8, c = 0.5, X = 1e-3 rad. Of 10 planned
cases that allows one failure, as `allowed_failures(10, 0.8, 0.5)` gives.
"""

import json
import re
from pathlib import Path

import h5py
import numpy as np
import pytest
from wise_dynamics.sessions import (
    crash_path,
    run_path,
    write_planned,
)

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
    """Write a run whose worst attitude error is `error_rad`, with no velocity or position error.

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
        for truth, estimate in (("v_N", "v_BN_N"), ("r_N", "r_BN_N")):
            f[f"truth/{truth}"] = np.zeros((5, 3))
            f[f"est/{estimate}"] = np.zeros((5, 3))


def write_cases(
    directory: Path,
    bad: tuple[int, ...] = (),
    crashed: tuple[int, ...] = (),
    missing: tuple[int, ...] = (),
    test: str = "test_tagged",
) -> None:
    """Write a test's session folder.

    Args:
        directory: the test's folder in a session.
        bad: cases whose run exceeds the threshold.
        crashed: cases with a crash record and no run file.
        missing: cases with neither file.
        test: the function the folder records.
    """
    write_planned(directory, PLANNED, f"tests/test_mc.py::{test}")
    for case in range(PLANNED):
        if case in missing:
            continue
        if case in crashed:
            crash_path(directory, case).write_text(json.dumps({"exception": "boom"}))
        else:
            write_run(run_path(directory, case), BAD_RAD if case in bad else GOOD_RAD)


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
    for name, value in (("X", "1e-3"), ("P", "0.8"), ("C", "0.5")):
        source, count = re.subn(rf"^{name} = .*$", f"{name} = {value}", source, flags=re.M)
        assert count == 1, name
    pytester.makefile(".ini", pytest="[pytest]\nmarkers =\n    verifies(*ids): a claim\n")
    conftest = (REPO / "analysis" / "conftest.py").read_text()
    pytester.makepyfile(
        **{
            "analysis/test_attitude_knowledge": source,
            "analysis/conftest": conftest,
            "tests/test_mc": MC,
        }
    )
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


def test_allowed_failures_matches_the_known_values(project: pytest.Pytester) -> None:
    """The rule reproduces the proposal's table, including the no-such-k case as None.

    Args:
        project: the project.
    """
    project.makepyfile(
        **{
            "analysis/test_rule": """\
import pytest


@pytest.mark.parametrize(
    ("n", "p", "c", "expected"),
    [(852, 0.99, 0.90, 4), (852, 0.9973, 0.90, 0), (851, 0.9973, 0.90, None)],
)
def test_rule(allowed_failures, n, p, c, expected):
    assert allowed_failures(n, p, c) == expected
"""
        }
    )

    project.runpytest_subprocess("analysis/test_rule.py", "-p", "no:xdist").assert_outcomes(
        passed=3
    )


def test_failures_within_the_allowance_pass(project: pytest.Pytester) -> None:
    """One failure of ten is allowed and the requirement passes.

    Args:
        project: the project.
    """
    write_cases(project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged", bad=(3,))

    judge(project).assert_outcomes(passed=1)


def test_a_crash_counts_as_a_failed_case(project: pytest.Pytester) -> None:
    """A crash and a bad run make two failures, over the allowance of one.

    Args:
        project: the project.
    """
    write_cases(
        project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged", bad=(3,), crashed=(5,)
    )

    result = judge(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*tests/test_mc.py::test_tagged: 2 failed, 1 allowed*"])
    test_matrix = project.path / "monte_carlo" / "s1" / "report" / "test_mc" / "test_tagged"
    assert (
        "| SRS001 | fail | 2/10/10 | 1 | 3, 5 (crash) |" in (test_matrix / "matrix.md").read_text()
    )


def test_failures_over_the_allowance_fail_and_name_the_cases(project: pytest.Pytester) -> None:
    """The requirement fails with a rerun command per failing case; both matrices record it.

    Args:
        project: the project.
    """
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged"
    write_cases(directory, bad=(2, 7))

    result = judge(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            '*case 2: uv run --no-sync pytest "tests/test_mc.py::test_tagged[[]2[]]" -n 0*',
            '*case 7: uv run --no-sync pytest "tests/test_mc.py::test_tagged[[]7[]]" -n 0*',
        ]
    )
    report = project.path / "monte_carlo" / "s1" / "report"
    test_matrix = (report / "test_mc" / "test_tagged" / "matrix.md").read_text()
    assert "| SRS001 | fail | 2/10/10 | 1 | 2, 7 |" in test_matrix
    assert "| SRS001 | fail, 2 of 1 allowed | fail |" in (report / "matrix.md").read_text()


def test_a_missing_case_leaves_the_requirement_not_judged(project: pytest.Pytester) -> None:
    """A case with neither run nor crash skips the requirement, naming the missing case.

    Args:
        project: the project.
    """
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged"
    write_cases(directory, bad=(2, 7), missing=(4,))

    result = judge(project)

    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*::test_tagged: missing cases [[]4[]]*"])


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
    assert not (directory.parents[1] / "report" / "test_mc" / "test_untagged").exists()


def test_requirements_judged_on_separate_workers_share_the_matrix(
    project: pytest.Pytester,
) -> None:
    """Each analyzer's cells reach `matrix.md` when xdist spreads the analyzers over workers.

    Args:
        project: the project.
    """
    for name in ("velocity", "position"):
        analyzer = f"test_{name}_knowledge.py"
        (project.path / "analysis" / analyzer).write_text(
            (REPO / "analysis" / analyzer).read_text()
        )
    claim_all = MC.replace('"SRS001"', '"SRS001", "SRS002", "SRS003"', 1)
    (project.path / "tests" / "test_mc.py").write_text(claim_all)
    write_cases(project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged")

    project.runpytest_subprocess("analysis", "-n", "3")

    matrix = (project.path / "monte_carlo" / "s1" / "report" / "matrix.md").read_text()
    assert [row.split(" | ")[0] for row in matrix.splitlines()[2:]] == [
        "| SRS001",
        "| SRS002",
        "| SRS003",
    ]


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
    assert (
        (report / "tests" / "test_mc" / "test_tagged" / "SRS001.png")
        .read_bytes()
        .startswith(b"\x89PNG")
    )
    test_matrix = (report / "tests" / "test_mc" / "test_tagged" / "matrix.md").read_text()
    assert "| SRS001 | pass | 0/4/4 | 0 |  |" in test_matrix
    rollup = (report / "matrix.md").read_text()
    assert "[test_tagged](tests/test_mc/test_tagged/matrix.md)" in rollup
    assert "| SRS001 | pass, 0 of 0 allowed | pass |" in rollup
