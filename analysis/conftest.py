"""Judge a Monte Carlo session against the requirements its tests claim with `verifies` marks.

An analyzer module declares `REQUIREMENT` and two tests, one taking `session_run` and one taking
`requirement_verdict`. Each (requirement, claiming test) pair is a cell. `session_run` is one item
per case of a cell, `requirement_verdict` the requirement as a whole, and `report/matrix.md` in the
session records every cell.
"""

import importlib.util
import math
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from wise_dynamics.sessions import TestResults, read_test_results, session_directory

from gnc_analysis.error_bounds import read_run
from gnc_analysis.requirements import Requirement, allowed_failures

NOT_APPLICABLE = "—"
HEADER = [
    "Requirement", "Test", "Verdict", "Failed", "Found", "Planned", "Allowed",
    "Failing cases", "Crashed cases",
]  # fmt: skip


def _join(cases: Any) -> str:
    """Case numbers as a comma-separated list.

    Args:
        cases: the case numbers.

    Returns:
        The ascending list, or an em dash when there are none.
    """
    return ", ".join(str(case) for case in sorted(cases)) or NOT_APPLICABLE


def _one_line(text: object) -> str:
    """Collapse whitespace so a message stays on one line.

    Args:
        text: the value to print.

    Returns:
        Its text on one line.
    """
    return " ".join(str(text).split())


@dataclass(frozen=True)
class MonteCarloTest:
    """A Monte Carlo test with a folder in the session.

    Attributes:
        directory: the test's folder in the session.
        path: the test's file, relative to the rootdir, without the suffix.
        names: the enclosing classes, then the function.
        ids: the requirement IDs its `verifies` marks claim.
        results: what the test left in `directory`.
    """

    directory: Path
    path: str
    names: tuple[str, ...]
    ids: frozenset[str]
    results: TestResults

    @property
    def label(self) -> str:
        """The test as `<module stem>.<function>`."""
        return f"{Path(self.path).name}.{self.names[-1]}"

    def rerun(self, case: int) -> str:
        """The command that runs one case alone.

        Args:
            case: the case number.

        Returns:
            The pytest command line.
        """
        node = "::".join(self.names)
        return f'pytest "{self.path}.py::{node}[{case}]" -n 0'


@dataclass(frozen=True)
class Cell:
    """One test's cases judged against one requirement.

    Attributes:
        test: the claiming test.
        allowed: the failures the requirement allows over `test.results.planned` cases, or None.
        metrics: case number to metric value, for the cases whose metric was computed.
        failures: case number to the reason, for the failed cases.
        missing: the planned cases with neither a run nor a crash record.
    """

    test: MonteCarloTest
    allowed: int | None
    metrics: dict[int, float]
    failures: dict[int, str]
    missing: list[int]

    @property
    def found(self) -> int:
        """The number of planned cases that left a run or a crash record."""
        return self.test.results.planned - len(self.missing)

    @property
    def why_not_judged(self) -> str | None:
        """Why the cell cannot be judged, or None when it can."""
        planned = self.test.results.planned
        if self.missing:
            return f"found {self.found} of {planned} cases, missing: {_join(self.missing)}"
        if self.allowed is None:
            return f"{planned} cases cannot show the reliability at the confidence"
        return None

    @property
    def passed(self) -> bool:
        """Whether the cell is judged and its failures are within the allowance."""
        return self.why_not_judged is None and len(self.failures) <= (self.allowed or 0)


def _evaluate(requirement: Requirement, test: MonteCarloTest) -> Cell:
    """Judge each case of a test against a requirement.

    Args:
        requirement: the requirement.
        test: the claiming test.

    Returns:
        The cell.
    """
    results = test.results
    metrics: dict[int, float] = {}
    failures: dict[int, str] = {}
    missing = []
    for case in range(results.planned):
        if case in results.runs:
            try:
                value = float(requirement.metric(read_run(results.runs[case])))
            except (OSError, KeyError, ValueError) as error:
                failures[case] = _one_line(f"run not usable: {error!r}")
                continue
            if math.isnan(value):
                failures[case] = "metric is NaN"
                continue
            metrics[case] = value
            if value > requirement.threshold:
                failures[case] = f"metric {value:.4g} exceeds {requirement.threshold:g}"
        elif case in results.crashes:
            failures[case] = _one_line(f"crashed: {results.crashes[case].get('exception')}")
        else:
            missing.append(case)
    allowed = allowed_failures(results.planned, requirement.p, requirement.c)
    return Cell(test, allowed, metrics, failures, missing)


def _verifies(chain: list[Any], where: str) -> frozenset[str]:
    """The requirement IDs the `verifies` marks of a module, its classes and its function claim.

    Args:
        chain: the module, then the classes, then the function.
        where: the test's name, for the error message.

    Returns:
        The IDs.

    Raises:
        TypeError: a `verifies` argument is not a non-empty string.
    """
    ids = set()
    for obj in chain:
        marks = getattr(obj, "pytestmark", [])
        for mark in marks if isinstance(marks, list) else [marks]:
            mark = getattr(mark, "mark", mark)
            if mark.name != "verifies":
                continue
            for arg in mark.args:
                if not isinstance(arg, str) or not arg:
                    raise TypeError(f"{where}: verifies takes non-empty strings, not {arg!r}")
                ids.add(arg)
    return frozenset(ids)


def _import(path: Path) -> ModuleType:
    """Import a Monte Carlo test's file.

    Args:
        path: the file.

    Returns:
        The module.

    Raises:
        ImportError: the file cannot be imported.
    """
    name = f"_monte_carlo_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise ImportError(f"cannot import the Monte Carlo test file {path}: {error!r}") from error
    return module


@dataclass
class Judging:
    """What one pytest run knows about the active session.

    Attributes:
        session: the session's folder.
        tests: the session's tagged Monte Carlo tests.
        requirements: the requirements whose analyzers ran, by ID.
        cells: each evaluated cell by (requirement ID, test folder).
    """

    session: Path
    tests: list[MonteCarloTest]
    requirements: dict[str, Requirement] = field(default_factory=dict)
    cells: dict[tuple[str, Path], Cell] = field(default_factory=dict)

    def claimers(self, requirement: Requirement) -> list[MonteCarloTest]:
        """The tests that claim a requirement.

        Args:
            requirement: the requirement.

        Returns:
            The tests, ordered by label.
        """
        return sorted((t for t in self.tests if requirement.id in t.ids), key=lambda t: t.label)

    def cell(self, requirement: Requirement, test: MonteCarloTest) -> Cell:
        """Judge a test against a requirement once.

        Args:
            requirement: the requirement.
            test: the claiming test.

        Returns:
            The cell.
        """
        key = (requirement.id, test.directory)
        if key not in self.cells:
            self.cells[key] = _evaluate(requirement, test)
        return self.cells[key]


def _discover(config: pytest.Config) -> Judging:
    """Find the active session's tagged Monte Carlo tests.

    A folder whose test no longer exists is listed in a warning and not judged. A test with no
    `verifies` mark is not judged.

    Args:
        config: the pytest configuration.

    Returns:
        The session's judging state.
    """
    session = session_directory(config)
    tests, vanished = [], []
    for planned in sorted(session.rglob("planned.json")):
        directory = planned.parent
        parts = directory.relative_to(session).parts
        found = None
        for split in range(len(parts) - 1, 0, -1):
            path = config.rootpath.joinpath(*parts[: split - 1], parts[split - 1] + ".py")
            if path.is_file():
                found = (path, parts[:split], parts[split:])
                break
        chain = None
        if found:
            path, prefix, names = found
            chain = [_import(path)]
            for name in names:
                chain.append(getattr(chain[-1], name, None))
        if not chain or chain[-1] is None:
            vanished.append(str(directory.relative_to(session)))
            continue
        ids = _verifies(chain, "/".join(parts))
        if ids:
            relative = path.relative_to(config.rootpath).with_suffix("").as_posix()
            tests.append(
                MonteCarloTest(directory, relative, names, ids, read_test_results(directory))
            )
    if vanished:
        warnings.warn(
            f"session folders whose Monte Carlo test no longer exists, not judged: {vanished}",
            UserWarning,
            stacklevel=2,
        )
    return Judging(session, tests)


JUDGING = pytest.StashKey[Judging]()


def _judging(config: pytest.Config) -> Judging:
    """The run's judging state, discovered on first use.

    Args:
        config: the pytest configuration.

    Returns:
        The judging state.
    """
    if JUDGING not in config.stash:
        config.stash[JUDGING] = _discover(config)
    return config.stash[JUDGING]


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Turn xdist off so a session is judged in one process wherever pytest is launched.

    Args:
        config: the pytest configuration.
    """
    config.option.dist = "no"


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize `session_run` over the cases of the tests that claim the module's requirement.

    Args:
        metafunc: the test function's metafunc.

    Raises:
        ValueError: two claiming tests give the same item id.
    """
    if "session_run" not in metafunc.fixturenames:
        return
    requirement = metafunc.module.REQUIREMENT
    judging = _judging(metafunc.config)
    judging.requirements[requirement.id] = requirement
    params, ids = [], []
    for test in judging.claimers(requirement):
        results = test.results
        for case in sorted(set(results.runs) | set(results.crashes)):
            params.append((test, case))
            ids.append(f"{test.label}-{case}")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"two Monte Carlo tests give the same item id: {duplicates}")
    if not judging.claimers(requirement):
        params, ids = [None], ["no-claim"]
    metafunc.parametrize("session_run", params, indirect=True, ids=ids)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Report a collection error for each `verifies` ID that no collected analyzer declares.

    Args:
        session: the pytest session.
        config: the pytest configuration.
        items: the collected items.
    """
    if JUDGING not in config.stash:
        return
    declared = {
        requirement.id
        for item in items
        if (requirement := getattr(getattr(item, "module", None), "REQUIREMENT", None))
    }
    claimed = {i for test in config.stash[JUDGING].tests for i in test.ids}
    unknown = sorted(claimed - declared)
    if unknown:
        text = f"verifies marks name requirements that no analyzer declares: {unknown}"
        report = pytest.CollectReport(session.nodeid or "analysis", "failed", text, [])
        config.hook.pytest_collectreport(report=report)


class SessionRun:
    """One case of a cell, or the single item for a requirement no test claims."""

    def __init__(self, judging: Judging, requirement: Requirement, case: tuple | None) -> None:
        """Bind the case.

        Args:
            judging: the run's judging state.
            requirement: the analyzer's requirement.
            case: the (claiming test, case number), or None when no test claims the requirement.
        """
        self.judging = judging
        self.requirement = requirement
        self.case = case

    def check(self) -> None:
        """Skip, pass, tolerate or fail this case.

        A cell that cannot be judged skips. A passing case returns. A failing case within the
        cell's allowance is an expected failure, and one beyond it fails.
        """
        if self.case is None:
            pytest.skip(
                f"no Monte Carlo test in session {self.judging.session.name} claims "
                f"{self.requirement.id}"
            )
        test, case = self.case
        cell = self.judging.cell(self.requirement, test)
        if cell.why_not_judged:
            pytest.skip(f"{test.label} not judged: {cell.why_not_judged}")
        reason = cell.failures.get(case)
        if reason is None:
            return
        planned = test.results.planned
        detail = f"{len(cell.failures)} of {planned} failed, {cell.allowed} allowed: {reason}"
        rerun = f"; rerun: {test.rerun(case)}"
        if len(cell.failures) <= cell.allowed:
            pytest.xfail(f"tolerated: {detail}{rerun}")
        pytest.fail(f"{detail}{rerun}")


class RequirementVerdict:
    """The requirement judged across its claiming tests."""

    def __init__(self, judging: Judging, requirement: Requirement) -> None:
        """Bind the requirement.

        Args:
            judging: the run's judging state.
            requirement: the analyzer's requirement.
        """
        self.judging = judging
        self.requirement = requirement
        self.cells = [judging.cell(requirement, t) for t in judging.claimers(requirement)]

    def plot(self, draw: Any) -> None:
        """Save the figure `draw` returns as `<session>/report/<ID>.png`.

        Nothing is drawn when no test claims the requirement.

        Args:
            draw: called as `draw(values, requirement)`, with the metrics by claiming test label
                and case, and returning a matplotlib figure.
        """
        if not self.cells:
            return
        import matplotlib.pyplot as plt

        values = {c.test.label: c.metrics for c in self.cells}
        figure = draw(values, self.requirement)
        report = self.judging.session / "report"
        report.mkdir(parents=True, exist_ok=True)
        figure.savefig(report / f"{self.requirement.id}.png")
        plt.close(figure)

    def check(self) -> None:
        """Fail when any judged cell fails, else skip when any cell is not judged, else pass."""
        judged = [c for c in self.cells if c.why_not_judged is None]
        failed = [c for c in judged if not c.passed]
        if failed:
            pytest.fail(
                f"{self.requirement.id} fails: "
                + "; ".join(
                    f"{c.test.label}: {len(c.failures)} of {c.test.results.planned} failed, "
                    f"{c.allowed} allowed"
                    for c in failed
                )
            )
        unjudged = [c for c in self.cells if c.why_not_judged is not None]
        if unjudged or not self.cells:
            session = self.judging.session.name
            reason = "; ".join(f"{c.test.label}: {c.why_not_judged}" for c in unjudged)
            pytest.skip(
                f"requirement {self.requirement.id} not judged: "
                + (reason or f"no Monte Carlo test in session {session} claims it")
            )


@pytest.fixture
def session_run(request: pytest.FixtureRequest) -> SessionRun:
    """The case under test.

    Args:
        request: the fixture request, whose param is the (test, case) or None.

    Returns:
        The case.
    """
    return SessionRun(_judging(request.config), request.module.REQUIREMENT, request.param)


@pytest.fixture
def requirement_verdict(request: pytest.FixtureRequest) -> RequirementVerdict:
    """The requirement under test.

    Args:
        request: the fixture request.

    Returns:
        The verdict.
    """
    return RequirementVerdict(_judging(request.config), request.module.REQUIREMENT)


def _row(requirement: Requirement, cell: Cell) -> list[str]:
    """One matrix row.

    Args:
        requirement: the requirement.
        cell: the cell.

    Returns:
        The row's cells, in the header's order.
    """
    results = cell.test.results
    if cell.why_not_judged:
        verdict, allowed = "NOT JUDGED", NOT_APPLICABLE
    else:
        verdict, allowed = ("PASS" if cell.passed else "FAIL"), str(cell.allowed)
    return [
        requirement.id,
        cell.test.label,
        verdict,
        str(len(cell.failures)),
        str(cell.found),
        str(results.planned),
        allowed,
        _join(cell.failures),
        _join(c for c in cell.failures if c in results.crashes and c not in results.runs),
    ]


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Write `<session>/report/matrix.md` when an analyzer ran.

    Args:
        session: the pytest session.
    """
    judging = session.config.stash.get(JUDGING, None)
    if judging is None or not judging.requirements:
        return
    ids = sorted(judging.requirements)
    lines = [f"Session: {judging.session.name} · judged: {', '.join(ids)}", ""]
    lines += ["| " + " | ".join(HEADER) + " |", "|" + "---|" * len(HEADER)]
    for id_ in ids:
        requirement = judging.requirements[id_]
        for test in judging.claimers(requirement):
            row = _row(requirement, judging.cell(requirement, test))
            lines.append("| " + " | ".join(row) + " |")
    report = judging.session / "report"
    report.mkdir(parents=True, exist_ok=True)
    (report / "matrix.md").write_text("\n".join(lines) + "\n")
