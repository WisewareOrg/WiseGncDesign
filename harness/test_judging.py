"""The requirement analyzers and their fixtures: cells, verdicts and the evidence they write.

Each fake requirement keeps a real analyzer's code with p = 0.8, c = 0.5, X = 1e-3 in its units.
Of 10 planned cases that allows one failure, as `allowed_failures(10, 0.8, 0.5)` gives.
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

REPO = Path(__file__).resolve().parents[1]
GOOD = 0.9e-3
BAD = 1.5e-3
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


def write_run(path: Path, error: float, kind: str = "attitude") -> None:
    """Write a run whose worst `kind` error is `error`, with no error of the other kinds.

    Args:
        path: the run file to create.
        error: the estimate's error at one sample, in rad, m/s or m.
        kind: "attitude", "velocity" or "position".
    """
    est = {name: np.zeros((5, 3)) for name in ("sigma_BN", "v_BN_N", "r_BN_N")}
    if kind == "attitude":
        est["sigma_BN"][2, 2] = np.tan(error / 4.0)
    else:
        est["v_BN_N" if kind == "velocity" else "r_BN_N"][2, 0] = error
    with h5py.File(path, "w") as f:
        f["t_s"] = np.linspace(0.0, 1.0, 5)
        for truth in ("sigma_BN", "v_N", "r_N"):
            f[f"truth/{truth}"] = np.zeros((5, 3))
        for name, values in est.items():
            f[f"est/{name}"] = values


def write_cases(
    directory: Path,
    bad: tuple[int, ...] = (),
    crashed: tuple[int, ...] = (),
    missing: tuple[int, ...] = (),
    test: str = "test_tagged",
    kind: str = "attitude",
    nan: tuple[int, ...] = (),
    planned: int = PLANNED,
) -> None:
    """Write a test's session folder.

    Args:
        directory: the test's folder in a session.
        bad: cases whose run exceeds the threshold.
        crashed: cases with a crash record and no run file.
        missing: cases with neither file.
        test: the function the folder records.
        kind: the error the runs carry, as `write_run` takes it.
        nan: cases whose error is NaN.
        planned: the planned case count.
    """
    write_planned(directory, planned, f"tests/test_mc.py::{test}")
    for case in range(planned):
        if case in missing:
            continue
        if case in crashed:
            crash_path(directory, case).write_text(json.dumps({"exception": "boom"}))
        else:
            error = np.nan if case in nan else BAD if case in bad else GOOD
            write_run(run_path(directory, case), error, kind)


def analyzer(name: str) -> str:
    """A real analyzer's source with X = 1e-3, p = 0.8 and c = 0.5.

    Args:
        name: "attitude", "velocity" or "position".

    Returns:
        The source.
    """
    source = (REPO / "analysis" / f"test_{name}_knowledge.py").read_text()
    for constant, value in (("X", "1e-3"), ("P", "0.8"), ("C", "0.5")):
        source, count = re.subn(rf"^{constant} = .*$", f"{constant} = {value}", source, flags=re.M)
        assert count == 1, constant
    return source


@pytest.fixture
def project(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A project holding the requirement test with p = 0.8, c = 0.5 and an empty session.

    Args:
        pytester: the pytester fixture.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The pytester, rooted in the project.
    """
    pytester.makefile(".ini", pytest="[pytest]\nmarkers =\n    verifies(*ids): a claim\n")
    conftest = (REPO / "analysis" / "conftest.py").read_text()
    pytester.makepyfile(
        **{
            "analysis/test_attitude_knowledge": analyzer("attitude"),
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
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged"
    write_cases(directory, bad=(3,))

    judge(project).assert_outcomes(passed=1)
    test_matrix = directory.parents[1] / "report" / "test_mc" / "test_tagged" / "matrix.md"
    assert "| SRS001 | pass | 1/10/10 | 1 | 3 |" in test_matrix.read_text()


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
    assert "| SRS001 | fail | 2/10/10 | 1 | 2, 7 |\n" in test_matrix
    rollup = (report / "matrix.md").read_text()
    assert "| SRS001 | [fail, 2 of 1 allowed](test_mc/test_tagged/SRS001.png) | fail |" in rollup


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


@pytest.mark.parametrize(("name", "requirement"), [("velocity", "SRS002"), ("position", "SRS003")])
def test_each_analyzer_judges_its_own_error(
    project: pytest.Pytester, name: str, requirement: str
) -> None:
    """The velocity and position analyzers read their own datasets and fail runs over X.

    Args:
        project: the project.
        name: the analyzer, and the kind of error its runs carry.
        requirement: the analyzer's requirement.
    """
    (project.path / "analysis" / "test_attitude_knowledge.py").unlink()
    (project.path / "analysis" / f"test_{name}_knowledge.py").write_text(analyzer(name))
    (project.path / "tests" / "test_mc.py").write_text(MC.replace("SRS001", requirement, 1))
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged"
    write_cases(directory, bad=(2, 7), kind=name)

    result = judge(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*tests/test_mc.py::test_tagged: 2 failed, 1 allowed*"])


def test_a_nan_error_counts_as_a_failed_case(project: pytest.Pytester) -> None:
    """A run whose error is NaN fails, so a diverged estimate cannot pass.

    Args:
        project: the project.
    """
    (project.path / "analysis" / "test_attitude_knowledge.py").unlink()
    (project.path / "analysis" / "test_velocity_knowledge.py").write_text(analyzer("velocity"))
    (project.path / "tests" / "test_mc.py").write_text(MC.replace("SRS001", "SRS002", 1))
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged"
    write_cases(directory, bad=(2,), nan=(5,), kind="velocity")

    result = judge(project)

    result.assert_outcomes(failed=1)
    test_matrix = directory.parents[1] / "report" / "test_mc" / "test_tagged" / "matrix.md"
    assert "| SRS002 | fail | 2/10/10 | 1 | 2, 5 |" in test_matrix.read_text()


def test_too_few_planned_cases_leave_the_requirement_not_judged(project: pytest.Pytester) -> None:
    """Three cases cannot show p = 0.8 at c = 0.5 even with no failure.

    Args:
        project: the project.
    """
    write_cases(project.path / "monte_carlo" / "s1" / "test_mc" / "test_tagged", planned=3)

    result = judge(project)

    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*test_tagged: 3 cases cannot show p=0.8 at c=0.5*"])


def test_a_class_claims_through_its_base_when_it_has_marks_of_its_own(
    project: pytest.Pytester,
) -> None:
    """A test class inherits its base class's `verifies` alongside a mark of its own.

    Args:
        project: the project.
    """
    (project.path / "tests" / "test_mc.py").write_text(
        "import pytest\n\n\n"
        '@pytest.mark.verifies("SRS001")\nclass Base:\n    pass\n\n\n'
        '@pytest.mark.verifies("SRS999")\nclass TestSub(Base):\n'
        "    def test_case(self):\n        pass\n"
    )
    directory = project.path / "monte_carlo" / "s1" / "test_mc" / "TestSub" / "test_case"
    write_cases(directory, test="TestSub::test_case")

    judge(project).assert_outcomes(passed=1)


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

    project.runpytest_subprocess("analysis", "-n", "3").assert_outcomes(passed=1, skipped=2)

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
    assert (
        "| SRS001 | [pass, 0 of 0 allowed](tests/test_mc/test_tagged/SRS001.png) | pass |" in rollup
    )
