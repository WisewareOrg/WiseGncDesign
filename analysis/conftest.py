"""The fixtures a requirement analyzer judges with, and the report's matrix.

An analyzer reads the runs `claimed_runs` names, computes its number for each and plots them, then
hands the numbers to `verdict`. `verdict` writes its cells to `report/<ID>.md`; `matrix.md` gathers
them once the run ends, so analyzers on separate xdist workers do not overwrite one another.
"""

import functools
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from matplotlib.figure import Figure
from scipy.stats import beta
from wise_dynamics.sessions import (
    CaseResults,
    NoSessionError,
    read_test_results,
    recorded_tests,
    session_directory,
)

HEADER = [
    "| Requirement | Test | Verdict | Failed/Found/Planned | Allowed | Failed cases |",
    "|---|---|---|---|---|---|",
]


@pytest.fixture
def claimed_runs(request: pytest.FixtureRequest) -> Callable[[str], dict[str, CaseResults]]:
    """A lookup of the active session's results by the requirement ID a test claims.

    A test claims an ID with `@pytest.mark.verifies("<ID>")` on its module, class or function.

    Args:
        request: the pytest request.

    Returns:
        A function mapping an ID to each claiming test's results by node ID.
    """
    session = session_directory(request.config)

    @functools.cache
    def lookup(requirement_id: str) -> dict[str, CaseResults]:
        """Each claiming test's results by node ID.

        Args:
            requirement_id: the ID the tests claim.

        Returns:
            The results by node ID.
        """
        found = {}
        for recorded in recorded_tests(session):
            file, *names = recorded.nodeid.split("::")
            path = Path(request.config.rootpath) / file
            name = f"_monte_carlo_{path.stem}"
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            chain = [module]
            for attribute in names:
                chain.append(getattr(chain[-1], attribute))
            for node in chain:
                marks = getattr(node, "pytestmark", [])
                for mark in marks if isinstance(marks, list) else [marks]:
                    if mark.name == "verifies" and requirement_id in mark.args:
                        found[recorded.nodeid] = read_test_results(recorded.directory)
        return found

    return lookup


@pytest.fixture
def allowed_failures() -> Callable[[int, float, float], int | None]:
    """The allowed-failures rule.

    Returns:
        `allowed_failures(n, p, c)`.
    """

    def allowed_failures(n: int, p: float, c: float) -> int | None:
        """The most failed runs out of `n` that still show reliability `p` at confidence `c`.

        The failure rate's one-sided Clopper-Pearson upper bound at confidence `c` must stay within
        `1 - p`.

        Args:
            n: the number of runs.
            p: the reliability the requirement demands, the share of runs that pass.
            c: the confidence the demonstration demands.

        Returns:
            The largest failure count `k` whose upper bound is within `1 - p`, or None when even
            zero failures cannot show `p` at `c` with `n` runs.
        """
        k = 0
        while k < n and beta.ppf(c, k + 1, n - k) <= 1.0 - p:
            k += 1
        return k - 1 if k > 0 else None

    return allowed_failures


@pytest.fixture
def verdict(
    request: pytest.FixtureRequest,
    claimed_runs: Callable[[str], dict[str, CaseResults]],
    allowed_failures: Callable[[int, float, float], int | None],
) -> Callable[[str, dict[str, dict[int, float]], float, float, float, dict[str, Figure]], None]:
    """Judge a requirement from its analyzer's number for each run, and write its report.

    Args:
        request: the pytest request.
        claimed_runs: the results of the tests claiming an ID.
        allowed_failures: the allowed-failures rule.

    Returns:
        `judge(requirement_id, numbers, x, p, c, figures)`, where `numbers` holds each claiming
        test's number by case. A case fails when its number is above `x` or it crashed.
    """
    session = Path(session_directory(request.config))
    report = session / "report"

    def judge(
        requirement_id: str,
        numbers: dict[str, dict[int, float]],
        x: float,
        p: float,
        c: float,
        figures: dict[str, Figure],
    ) -> None:
        """Give each claiming test a cell, write the report, then fail or skip unless all pass.

        A test's cell is not judged when a planned case has neither a run nor a crash record, or
        when no failure count shows `p` at `c`; it fails when more cases fail than are allowed.

        Args:
            requirement_id: the requirement.
            numbers: each claiming test's number by case.
            x: the largest number a passing run may have.
            p: the share of runs that must pass.
            c: the confidence the demonstration demands.
            figures: each claiming test's plot, saved as `<ID>.png` under the report's copy
                of the test's folder in the session.
        """
        rows, failing, unjudged = list(HEADER), [], []
        for nodeid, results in claimed_runs(requirement_id).items():
            failed = sorted(
                [case for case, number in numbers[nodeid].items() if number > x]
                + list(results.crashes)
            )
            found = len(results.runs) + len(results.crashes)
            missing = [
                case
                for case in range(results.planned)
                if case not in results.runs and case not in results.crashes
            ]
            allowed = allowed_failures(results.planned, p, c)
            if missing:
                cell = "not judged"
                unjudged.append(f"{nodeid}: missing cases {missing}")
            elif allowed is None:
                cell = "not judged"
                unjudged.append(f"{nodeid}: {results.planned} cases cannot show p={p} at c={c}")
            elif len(failed) > allowed:
                cell = "fail"
                failing.append(f"{nodeid}: {len(failed)} failed, {allowed} allowed")
                failing += [
                    f'  case {case}: uv run --no-sync pytest "{nodeid}[{case}]" -n 0'
                    for case in failed
                ]
            else:
                cell = "pass"
            listed = ", ".join(
                f"{case} (crash)" if case in results.crashes else str(case) for case in failed
            )
            rows.append(
                f"| {requirement_id} | {nodeid} | {cell} | {len(failed)}/{found}/{results.planned}"
                f" | {allowed} | {listed} |"
            )
        report.mkdir(parents=True, exist_ok=True)
        folders = {test.nodeid: test.directory for test in recorded_tests(session)}
        for nodeid, figure in figures.items():
            folder = report / folders[nodeid].relative_to(session)
            folder.mkdir(parents=True, exist_ok=True)
            figure.savefig(folder / f"{requirement_id}.png")
        (report / f"{requirement_id}.md").write_text("\n".join(rows) + "\n")
        if failing:
            pytest.fail(f"{requirement_id} failed\n" + "\n".join(failing))
        if unjudged:
            pytest.skip(f"{requirement_id} not judged: " + "; ".join(unjudged))
        if len(rows) == len(HEADER):
            pytest.skip(f"{requirement_id} not judged: no test claims it")

    return judge


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Gather each requirement's table in the active session's report into `matrix.md`.

    Nothing is written on an xdist worker or when no session is active.

    Args:
        session: the pytest session.
    """
    if hasattr(session.config, "workerinput"):
        return
    try:
        report = Path(session_directory(session.config)) / "report"
    except NoSessionError:
        return
    tables = sorted(t for t in report.glob("*.md") if t.name != "matrix.md")
    if tables:
        header = tables[0].read_text().splitlines()[:2]
        rows = header + [row for t in tables for row in t.read_text().splitlines()[2:]]
        (report / "matrix.md").write_text("\n".join(rows) + "\n")
