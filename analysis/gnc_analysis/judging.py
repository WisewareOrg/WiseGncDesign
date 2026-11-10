"""Judge Monte Carlo test results against requirements.

A cell is one claiming test's cases judged against one requirement. `SessionRun` is one case of a
cell and `RequirementVerdict` the requirement across its cells. The pytest hooks and fixtures that
build them are in `analysis/conftest.py`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from gnc_analysis.error_bounds import read_run
from gnc_analysis.requirements import Requirement, allowed_failures

if TYPE_CHECKING:
    from matplotlib.figure import Figure
    from wise_dynamics.sessions import CaseResults

NOT_APPLICABLE = "—"


def join_cases(cases: Iterable[int]) -> str:
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
        file: the test's file, relative to the rootdir.
        names: the enclosing classes, then the function.
        ids: the requirement IDs its `verifies` marks claim.
        results: what the test left in `directory`.
    """

    directory: Path
    file: Path
    names: tuple[str, ...]
    ids: frozenset[str]
    results: CaseResults

    @property
    def label(self) -> str:
        """The test as `<module stem>.<function>`."""
        return f"{self.file.stem}.{self.names[-1]}"

    def rerun(self, case: int) -> str:
        """The command that runs one case alone.

        Args:
            case: the case number.

        Returns:
            The pytest command line.
        """
        node = "::".join(self.names)
        return f'pytest "{self.file.as_posix()}::{node}[{case}]" -n 0'


@dataclass(frozen=True)
class Cell:
    """One test's cases judged against one requirement.

    Attributes:
        requirement: the requirement.
        test: the claiming test.
        allowed: the failures the requirement allows over `test.results.planned` cases, or None.
        metrics: case number to metric value, for the cases whose metric was computed.
        failures: case number to the reason, for the failed cases.
        crashed: the failed cases that crashed and left no run.
        missing: the planned cases with neither a run nor a crash record.
    """

    requirement: Requirement
    test: MonteCarloTest
    allowed: int | None
    metrics: dict[int, float]
    failures: dict[int, str]
    crashed: list[int]
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
            return f"found {self.found} of {planned} cases, missing: {join_cases(self.missing)}"
        if self.allowed is None:
            p, c = self.requirement.p, self.requirement.c
            return f"{planned} cases cannot show reliability {p:g} at confidence {c:g}"
        return None

    @property
    def passed(self) -> bool:
        """Whether the cell is judged and its failures are within the allowance."""
        return self.why_not_judged is None and len(self.failures) <= self.allowed


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
    crashed = []
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
            crashed.append(case)
        else:
            missing.append(case)
    allowed = allowed_failures(results.planned, requirement.p, requirement.c)
    return Cell(requirement, test, allowed, metrics, failures, crashed, missing)


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


class SessionRun:
    """One case of a cell, or the single item for a requirement no test claims."""

    def __init__(
        self,
        judging: Judging,
        requirement: Requirement,
        claim: tuple[MonteCarloTest, int] | None,
    ) -> None:
        """Bind the case.

        Args:
            judging: the run's judging state.
            requirement: the analyzer's requirement.
            claim: the (claiming test, case number), or None when no test claims the requirement.
        """
        self.judging = judging
        self.requirement = requirement
        self.claim = claim

    def check(self) -> None:
        """Skip, pass, tolerate or fail this case.

        A cell that cannot be judged skips. A passing case returns. A failing case within the
        cell's allowance is an expected failure, and one beyond it fails.
        """
        if self.claim is None:
            pytest.skip(
                f"no Monte Carlo test in session {self.judging.session.name} claims "
                f"{self.requirement.id}"
            )
        test, case = self.claim
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

    def plot(self, draw: Callable[[dict[str, dict[int, float]], Requirement], Figure]) -> None:
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
        if not self.cells:
            pytest.skip(
                f"{self.requirement.id} verdict not judged: no Monte Carlo test in session "
                f"{self.judging.session.name} claims it"
            )
        unjudged = [c for c in self.cells if c.why_not_judged is not None]
        if unjudged:
            reason = "; ".join(f"{c.test.label}: {c.why_not_judged}" for c in unjudged)
            pytest.skip(f"{self.requirement.id} verdict not judged: {reason}")
