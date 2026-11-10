"""The requirement analyzer: `analysis/conftest.py` judges a session against `verifies` marks.

Each test builds a throwaway project holding a copy of the real `analysis/conftest.py`, a fake
Monte Carlo test module, a fake requirement analyzer and a hand-written session, then runs pytest
over `analysis` in a subprocess and reads the outcome of each item.

The fake requirement is `REQ1` with threshold 1e-3 rad, p = 0.8, c = 0.5. Of 10 planned cases that
allows one failure, as `allowed_failures(10, 0.8, 0.5)` gives: the largest k with
`binom.cdf(k, 10, 0.2) <= 0.5` is 1.
"""

import json
import re
from pathlib import Path

import h5py
import numpy as np
import pytest
from wise_dynamics.sessions import crash_path, run_path, write_planned

REPO = Path(__file__).resolve().parents[2]
GOOD_RAD = 0.9e-3
BAD_RAD = 1.5e-3
PLANNED = 10
ALLOWED = 1
ID_RE = re.compile(r"::test_fake\[(?P<id>[^\]]+)\] (?P<word>PASSED|FAILED|XFAIL|SKIPPED|ERROR)")

PYTEST_INI = """\
[pytest]
addopts = -n 2
markers =
    verifies(*ids): the requirements a Monte Carlo test verifies
"""

FAKE_MC = '''\
"""A fake Monte Carlo test module."""

import pytest


@pytest.mark.verifies("REQ1")
def test_func():
    """Tagged."""


def test_untagged():
    """Not tagged."""


@pytest.mark.verifies("REQ1")
class TestKlass:
    """Tagged at class level."""

    def test_in_class(self):
        """Inherits the class's tag."""
'''

FAKE_ANALYZER = '''\
"""A fake requirement analyzer."""

import os
from pathlib import Path

from gnc_analysis.requirements import Requirement, worst_attitude_error_rad

Path(os.environ["IMPORT_LOG"]).open("a").write(
    os.environ.get("PYTEST_XDIST_WORKER", "none") + "\\n"
)

REQUIREMENT = Requirement(
    id="REQ1",
    statement="Attitude error shall stay small.",
    threshold=1e-3,
    p=0.8,
    c=0.5,
    metric=worst_attitude_error_rad,
)


def plot_it(values, requirement):
    """Record what the plot function was given, and draw."""
    import json
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    record = {
        "values": {t: {str(c): v for c, v in cs.items()} for t, cs in values.items()},
        "id": requirement.id,
    }
    Path(os.environ["PLOT_LOG"]).write_text(json.dumps(record))
    figure = plt.figure()
    figure.gca().plot([0, 1])
    return figure


def test_fake(session_run):
    """One item per run."""
    session_run.check()


def test_fake_verdict(requirement_verdict):
    """The verdict."""
    requirement_verdict.plot(plot_it)
    requirement_verdict.check()
'''


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


class Project:
    """A throwaway project holding the analyzer under test and a session."""

    def __init__(self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lay out the project, with no cases yet.

        Args:
            pytester: the pytester fixture.
            monkeypatch: the monkeypatch fixture.
        """
        conftest = REPO / "analysis" / "conftest.py"
        assert conftest.is_file(), "analysis/conftest.py does not exist"
        self.pytester = pytester
        self.root = pytester.path
        self.import_log = pytester.path / "imports.log"
        pytester.makefile(".ini", pytest=PYTEST_INI)
        pytester.makepyfile(**{"tests/test_mc": FAKE_MC})
        pytester.makepyfile(**{"analysis/test_fake": FAKE_ANALYZER})
        (self.root / "analysis" / "conftest.py").write_text(conftest.read_text())
        (self.root / "monte_carlo").mkdir()
        (self.root / "monte_carlo" / "SESSION").write_text("s1\n")
        self.session = self.root / "monte_carlo" / "s1"
        for name in ("PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("IMPORT_LOG", str(self.import_log))
        monkeypatch.setenv("COLUMNS", "400")
        self.plot_log = pytester.path / "plot.json"
        monkeypatch.setenv("PLOT_LOG", str(self.plot_log))

    def cases(
        self,
        folder: str,
        *,
        planned: int = PLANNED,
        bad: tuple[int, ...] = (),
        crashed: tuple[int, ...] = (),
        missing: tuple[int, ...] = (),
        stale: tuple[int, ...] = (),
        garbage: tuple[int, ...] = (),
    ) -> Path:
        """Write one test's session folder.

        Args:
            folder: the folder under the session, `<file>/<class>/<function>`.
            planned: the count in `planned.json`.
            bad: cases whose run exceeds the threshold.
            crashed: cases with a crash record and no run file.
            missing: cases with neither file.
            stale: case numbers at or above `planned` that get a failing run file.
            garbage: cases whose run file is not an HDF5 file.

        Returns:
            The folder.
        """
        directory = self.session / folder
        directory.mkdir(parents=True)
        file, *names = folder.split("/")[1:]
        nodeid = "::".join([f"tests/{file}.py", *names])
        write_planned(directory, planned, nodeid)
        for case in range(planned):
            if case in missing:
                continue
            if case in crashed:
                record = {"exception": "RuntimeError('boom')", "traceback": "Traceback..."}
                crash_path(directory, case).write_text(json.dumps(record))
            elif case in garbage:
                run_path(directory, case).write_bytes(b"not hdf5")
            else:
                write_run(run_path(directory, case), BAD_RAD if case in bad else GOOD_RAD)
        for case in stale:
            write_run(run_path(directory, case), BAD_RAD)
        return directory

    def judge(self, *args: str) -> pytest.RunResult:
        """Run pytest over `analysis` in a subprocess.

        Args:
            *args: extra pytest arguments.

        Returns:
            The run's result.
        """
        return self.pytester.runpytest_subprocess("analysis", "-v", "-rxs", "--tb=line", *args)


@pytest.fixture
def project(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Project:
    """A project with the analyzer, the fake Monte Carlo module and an empty session.

    Args:
        pytester: the pytester fixture.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The project.
    """
    return Project(pytester, monkeypatch)


def outcomes(result: pytest.RunResult) -> dict[str, str]:
    """Each `test_fake` item's outcome word by its id.

    Args:
        result: a judge run.

    Returns:
        The outcome word of each item by the id inside its brackets.
    """
    return {m["id"]: m["word"] for m in ID_RE.finditer(result.stdout.str())}


def verdict(result: pytest.RunResult) -> str:
    """The `test_fake_verdict` item's outcome word.

    Args:
        result: a judge run.

    Returns:
        The word.
    """
    found = re.search(
        r"::test_fake_verdict (PASSED|FAILED|XFAIL|SKIPPED|ERROR)", result.stdout.str()
    )
    assert found, result.stdout.str()
    return found.group(1)


FUNC = "tests/test_mc/test_func"
KLASS = "tests/test_mc/TestKlass/test_in_class"


def test_all_cases_inside_the_threshold_pass(project: Project) -> None:
    """Every run is PASSED, a case at 0.9 of X included, and the verdict passes.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC)

    result = project.judge()

    assert outcomes(result) == {f"test_mc.test_func-{i}": "PASSED" for i in range(PLANNED)}
    assert verdict(result) == "PASSED"
    result.assert_outcomes(passed=PLANNED + 1)


def test_failures_within_the_allowance_are_xfail_and_the_verdict_passes(project: Project) -> None:
    """One bad run of ten, one allowed, is XFAIL with the tolerated message; the verdict passes.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3,))

    result = project.judge()

    got = outcomes(result)
    assert got["test_mc.test_func-3"] == "XFAIL"
    assert [i for i, w in got.items() if w == "PASSED"] == [
        f"test_mc.test_func-{i}" for i in range(PLANNED) if i != 3
    ]
    assert verdict(result) == "PASSED"
    result.assert_outcomes(passed=PLANNED, xfailed=1)
    xfail_lines = [ln for ln in result.stdout.lines if ln.startswith("XFAIL") and "-3]" in ln]
    assert len(xfail_lines) == 1
    assert f"tolerated: 1 of {PLANNED} failed, {ALLOWED} allowed" in xfail_lines[0]
    assert xfail_lines[0].rstrip().endswith('; rerun: pytest "tests/test_mc.py::test_func[3]" -n 0')


def test_failures_over_the_allowance_fail_every_failing_run_and_the_verdict(
    project: Project,
) -> None:
    """Two bad runs of ten, one allowed, are both FAILED and the verdict fails.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3, 7))

    result = project.judge()

    got = outcomes(result)
    assert got["test_mc.test_func-3"] == got["test_mc.test_func-7"] == "FAILED"
    assert verdict(result) == "FAILED"
    result.assert_outcomes(passed=PLANNED - 2, failed=3)


def test_a_failing_item_message_ends_with_the_command_that_reruns_the_case(
    project: Project,
) -> None:
    """Each FAILED run's message ends with its own `rerun: pytest "<node>" -n 0` command.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3, 7))

    result = project.judge()

    lines = [ln.rstrip() for ln in result.stdout.lines]
    for case in (3, 7):
        command = f'rerun: pytest "tests/test_mc.py::test_func[{case}]" -n 0'
        assert any(ln.endswith(command) for ln in lines), command


def test_a_class_level_rerun_command_names_the_class(project: Project) -> None:
    """The rerun command of a test in a class carries `Class::` before the function.

    Args:
        project: the throwaway project.
    """
    project.cases(KLASS, bad=(2, 5))

    result = project.judge()

    command = 'rerun: pytest "tests/test_mc.py::TestKlass::test_in_class[2]" -n 0'
    assert any(ln.rstrip().endswith(command) for ln in result.stdout.lines)


def test_a_crash_record_counts_as_a_failed_case(project: Project) -> None:
    """A crash within the allowance is XFAIL, and with one bad run beyond it both are FAILED.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, crashed=(4,))
    within = project.judge()
    assert outcomes(within)["test_mc.test_func-4"] == "XFAIL"
    assert verdict(within) == "PASSED"

    (project.session / FUNC / "run_0006.h5").unlink()
    write_run(project.session / FUNC / "run_0006.h5", BAD_RAD)
    over = project.judge()

    got = outcomes(over)
    assert got["test_mc.test_func-4"] == got["test_mc.test_func-6"] == "FAILED"
    assert verdict(over) == "FAILED"


@pytest.mark.parametrize("damage", ["garbage", "no-data", "nan"])
def test_an_unusable_run_counts_as_a_failed_case(project: Project, damage: str) -> None:
    """A run that cannot be read, lacks the metric's data, or gives NaN is one failed case.

    Args:
        project: the throwaway project.
        damage: how case 2's run is spoiled.
    """
    directory = project.cases(FUNC, garbage=(2,) if damage == "garbage" else ())
    if damage == "no-data":
        with h5py.File(directory / "run_0002.h5", "w") as f:
            f["t_s"] = np.zeros(2)
    if damage == "nan":
        with h5py.File(directory / "run_0002.h5", "w") as f:
            f["t_s"] = np.zeros(2)
            f["truth/sigma_BN"] = np.zeros((2, 3))
            f["est/sigma_BN"] = np.full((2, 3), np.nan)

    result = project.judge()

    assert outcomes(result)["test_mc.test_func-2"] == "XFAIL"
    assert verdict(result) == "PASSED"


def test_a_missing_case_leaves_the_cell_not_judged_and_lists_the_case(project: Project) -> None:
    """With case 4 absent every item of the cell is skipped, saying found 9 of 10 and case 4.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(1, 2, 3), missing=(4,))

    result = project.judge()

    assert set(outcomes(result).values()) == {"SKIPPED"}
    assert verdict(result) == "SKIPPED"
    result.assert_outcomes(skipped=PLANNED)
    reasons = [ln for ln in result.stdout.lines if ln.startswith("SKIPPED")]
    assert reasons
    assert all(f"found {PLANNED - 1} of {PLANNED} cases, missing: 4" in ln for ln in reasons)
    row = matrix_rows(project)["test_mc.test_func"]
    assert row["Verdict"] == "NOT JUDGED"
    assert (row["Found"], row["Planned"], row["Allowed"]) == ("9", "10", "—")


def test_an_untagged_test_is_not_judged(project: Project) -> None:
    """A session folder of a test with no `verifies` mark yields no items and no matrix row.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC)
    project.cases("tests/test_mc/test_untagged", bad=(0, 1, 2))

    result = project.judge()

    assert "test_untagged" not in "".join(outcomes(result))
    result.assert_outcomes(passed=PLANNED + 1)
    assert "test_untagged" not in (project.session / "report" / "matrix.md").read_text()


def test_a_requirement_passes_only_when_every_claiming_cell_passes(project: Project) -> None:
    """A failing cell of a class-marked test fails the verdict beside a cell inside its allowance.

    The class-level `verifies` mark is what makes the `TestKlass` cell judged at all.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3,))
    project.cases(KLASS, bad=(3, 4))

    result = project.judge()

    assert outcomes(result)["test_mc.test_func-3"] == "XFAIL"
    assert outcomes(result)["test_mc.test_in_class-3"] == "FAILED"
    assert verdict(result) == "FAILED"


def test_a_not_judged_cell_keeps_the_requirement_from_passing(project: Project) -> None:
    """One cell passing and one missing a case leave the verdict skipped, naming the missing cell.

    A requirement fails if any judged cell fails, otherwise is not judged if any cell is not
    judged, otherwise passes (issue 27, design ruling D17).

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC)
    project.cases(KLASS, missing=(4,))

    result = project.judge()

    assert outcomes(result)["test_mc.test_func-0"] == "PASSED"
    assert verdict(result) == "SKIPPED"
    reasons = [ln for ln in result.stdout.lines if ln.startswith("SKIPPED") and "verdict" in ln]
    assert len(reasons) == 1
    assert "test_in_class" in reasons[0]


def test_an_unknown_verifies_id_is_a_usage_error_and_nothing_runs(project: Project) -> None:
    """A test claiming an ID no analyzer declares stops pytest with exit code 4, naming the ID.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC)
    mc = project.root / "tests" / "test_mc.py"
    mc.write_text(mc.read_text().replace('verifies("REQ1")\ndef', 'verifies("NOPE")\ndef'))

    result = project.judge()

    assert result.ret == 4
    assert "NOPE" in result.stdout.str() + result.stderr.str()
    assert outcomes(result) == {}
    assert not {"passed", "failed", "skipped", "xfailed"} & result.parseoutcomes().keys()


@pytest.mark.parametrize(
    ("replacement", "message"),
    [("7", "verifies takes non-empty strings"), ('""', "verifies takes non-empty strings")],
    ids=["integer", "empty-string"],
)
def test_a_verifies_argument_that_is_not_a_non_empty_string_is_an_error(
    project: Project, replacement: str, message: str
) -> None:
    """A `verifies` argument of 7 or "" errors, naming the rule, and no case is judged.

    Args:
        project: the throwaway project.
        replacement: the text put in place of the first mark's `"REQ1"`.
        message: what the error must say.
    """
    project.cases(FUNC)
    mc = project.root / "tests" / "test_mc.py"
    mc.write_text(mc.read_text().replace('verifies("REQ1")\ndef', f"verifies({replacement})\ndef"))

    result = project.judge()

    assert result.ret != 0
    assert message in result.stdout.str() + result.stderr.str()
    assert outcomes(result) == {}


def test_a_monte_carlo_test_file_that_cannot_be_imported_is_an_error(project: Project) -> None:
    """A session folder whose test file raises on import errors, naming the file; nothing runs.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC)
    mc = project.root / "tests" / "test_mc.py"
    mc.write_text('raise RuntimeError("broken at import")\n')

    result = project.judge()

    out = result.stdout.str() + result.stderr.str()
    assert result.ret != 0
    assert "cannot import the Monte Carlo test file" in out
    assert "broken at import" in out
    assert outcomes(result) == {}


def test_a_failing_cell_beats_a_not_judged_cell(project: Project) -> None:
    """One cell over its allowance and one missing a case fail the verdict, not skip it.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3, 7))
    project.cases(KLASS, missing=(4,))

    result = project.judge()

    assert verdict(result) == "FAILED"


def test_a_cell_with_too_few_planned_cases_to_show_the_claim_is_not_judged(
    project: Project,
) -> None:
    """Three planned cases cannot show p = 0.8 at c = 0.5, so the cell is skipped and says why.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, planned=3)

    result = project.judge()

    assert set(outcomes(result).values()) == {"SKIPPED"}
    assert verdict(result) == "SKIPPED"
    reasons = [ln for ln in result.stdout.lines if ln.startswith("SKIPPED")]
    assert reasons
    assert all("3 cases cannot show reliability 0.8 at confidence 0.5" in ln for ln in reasons)
    row = matrix_rows(project)["test_mc.test_func"]
    assert (row["Verdict"], row["Found"], row["Planned"], row["Allowed"]) == (
        "NOT JUDGED",
        "3",
        "3",
        "—",
    )


def test_a_session_folder_whose_test_no_longer_exists_is_warned_about_and_not_judged(
    project: Project,
) -> None:
    """A folder for a missing file or a missing function warns, naming it, and yields no item.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC)
    project.cases("tests/test_gone/test_x", bad=(0, 1, 2))
    project.cases("tests/test_mc/test_renamed_away", bad=(0, 1, 2))

    result = project.judge()

    out = result.stdout.str()
    assert "Monte Carlo test does not exist, not judged" in out
    assert "tests/test_gone/test_x" in out
    assert "tests/test_mc/test_renamed_away" in out
    assert set(outcomes(result)) == {f"test_mc.test_func-{i}" for i in range(PLANNED)}
    assert verdict(result) == "PASSED"
    assert set(matrix_rows(project)) == {"test_mc.test_func"}


def test_judging_with_no_active_session_errors_naming_the_option(
    project: Project,
) -> None:
    """With no session pointer and no `--sim-session`, pytest errors naming it and runs nothing.

    Args:
        project: the throwaway project.
    """
    (project.root / "monte_carlo" / "SESSION").unlink()

    result = project.judge()

    assert result.ret != 0
    assert "--sim-session" in result.stdout.str() + result.stderr.str()
    assert outcomes(result) == {}


def test_a_requirement_no_test_claims_is_one_skipped_item(project: Project) -> None:
    """With only an untagged test in the session, the item is skipped saying nothing claims REQ1.

    Args:
        project: the throwaway project.
    """
    project.cases("tests/test_mc/test_untagged")

    result = project.judge()

    out = result.stdout.str()
    assert "no Monte Carlo test in session s1 claims REQ1" in out
    counts = result.parseoutcomes()
    assert counts.get("skipped", 0) >= 1
    assert not {"passed", "failed", "error", "errors"} & counts.keys()


def test_cases_at_or_above_planned_are_ignored(project: Project) -> None:
    """A stale failing run_0012 beside a planned count of 10 produces no item and no failure.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, stale=(12, 13))

    result = project.judge()

    assert set(outcomes(result)) == {f"test_mc.test_func-{i}" for i in range(PLANNED)}
    assert verdict(result) == "PASSED"
    result.assert_outcomes(passed=PLANNED + 1)


def test_xdist_in_addopts_still_judges_in_one_process(project: Project) -> None:
    """With `-n 2` in addopts the analyzer module is imported once, outside any xdist worker.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3,))

    result = project.judge()

    result.assert_outcomes(passed=PLANNED, xfailed=1)
    assert project.import_log.read_text().split() == ["none"]


def matrix_rows(project: Project) -> dict[str, dict[str, str]]:
    """The matrix table's rows by their Test cell, each as header to cell text.

    Args:
        project: the throwaway project.

    Returns:
        Each row as header to cell text, by its Test cell.
    """
    lines = (project.session / "report" / "matrix.md").read_text().splitlines()
    table = [ln for ln in lines if ln.startswith("|")]
    header = [c.strip() for c in table[0].strip("|").split("|")]
    assert header == [
        "Requirement", "Test", "Verdict", "Failed", "Found", "Planned", "Allowed",
        "Failing cases", "Crashed cases",
    ]  # fmt: skip
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in table[2:]]
    return {r[1]: dict(zip(header, r, strict=True)) for r in rows}


def cases_in(cell: str) -> list[str]:
    """The case numbers of a matrix list cell, empty for an em dash.

    Args:
        cell: the cell's text.

    Returns:
        The case numbers as text.
    """
    return [] if cell == "—" else [c.strip() for c in cell.split(",")]


def test_matrix_has_a_header_and_one_row_per_requirement_and_claiming_test(
    project: Project,
) -> None:
    """`report/matrix.md` names the judged requirements, then one filled row per cell.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3,), crashed=(5,))
    project.cases(KLASS)

    project.judge()

    lines = (project.session / "report" / "matrix.md").read_text().splitlines()
    assert lines[0] == "Session: s1 · judged: REQ1"
    assert lines[1] == ""
    rows = matrix_rows(project)
    assert set(rows) == {"test_mc.test_func", "test_mc.test_in_class"}
    func = rows["test_mc.test_func"]
    assert func["Requirement"] == "REQ1"
    assert func["Verdict"] == "FAIL"
    assert (func["Failed"], func["Found"], func["Planned"], func["Allowed"]) == (
        "2",
        "10",
        "10",
        "1",
    )
    assert cases_in(func["Failing cases"]) == ["3", "5"]
    assert cases_in(func["Crashed cases"]) == ["5"]
    klass = rows["test_mc.test_in_class"]
    assert klass["Verdict"] == "PASS"
    assert (klass["Failed"], klass["Found"], klass["Planned"], klass["Allowed"]) == (
        "0",
        "10",
        "10",
        "1",
    )
    assert cases_in(klass["Failing cases"]) == cases_in(klass["Crashed cases"]) == []


def test_the_verdict_plots_the_computed_metrics_and_writes_the_png(project: Project) -> None:
    """The plot function gets the metrics of cases that computed one, and its figure is saved.

    Args:
        project: the throwaway project.
    """
    project.cases(FUNC, bad=(3,), crashed=(5,))

    project.judge()

    record = json.loads(project.plot_log.read_text())
    assert record["id"] == "REQ1"
    assert set(record["values"]) == {"test_mc.test_func"}
    metrics = record["values"]["test_mc.test_func"]
    assert set(metrics) == {str(i) for i in range(PLANNED) if i != 5}
    assert metrics["3"] == pytest.approx(BAD_RAD, abs=1e-9)
    assert metrics["0"] == pytest.approx(GOOD_RAD, abs=1e-9)
    png = project.session / "report" / "REQ1.png"
    assert png.read_bytes().startswith(b"\x89PNG")


SIM_TEST = '''\
"""A Monte Carlo test run by the WiseDynamics plugin."""

import numpy as np
import pytest


@pytest.mark.verifies("REQ1")
@pytest.mark.sim_runs(4)
@pytest.mark.sim_duration_s(3)
def test_func(sim_run_file):
    """Four cases, each a run file with a small constant attitude error."""
    est = np.zeros((5, 3))
    est[2, 2] = np.tan(0.9e-3 / 4.0)
    sim_run_file(
        {
            "t_s": (np.linspace(0.0, 1.0, 5), "s"),
            "truth/sigma_BN": (np.zeros((5, 3)), "-"),
            "est/sigma_BN": (est, "-"),
        }
    )
'''


def test_a_session_written_by_the_wise_dynamics_plugin_is_judged(project: Project) -> None:
    """A real `sim_` test's session, run through the plugin, is found and judged by the analyzer.

    This backs the hand-built sessions of the other tests with the layout the plugin writes. Four
    planned cases are the fewest that can show p = 0.8 at c = 0.5.

    Args:
        project: the throwaway project.
    """
    (project.root / "tests" / "test_mc.py").write_text(SIM_TEST)
    out = ("-o", "sim_out=monte_carlo")
    project.pytester.runpytest_subprocess("--sim-session", "s1", *out)
    simulated = project.pytester.runpytest_subprocess("tests/test_mc.py", *out, "-n", "0")
    simulated.assert_outcomes(passed=4)

    result = project.judge()

    assert outcomes(result) == {f"test_mc.test_func-{i}": "PASSED" for i in range(4)}
    assert verdict(result) == "PASSED"
    assert "does not exist" not in result.stdout.str()
    assert set(matrix_rows(project)) == {"test_mc.test_func"}
