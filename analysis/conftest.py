"""The fixtures a requirement analyzer judges with, and the report's matrices.

An analyzer reads the runs `claimed_runs` names, computes its number for each and plots one figure
per claiming test, then hands both to `verdict`. `verdict` writes each cell and its plot into the
report, under the same path as the test's runs in the session. The matrices are written from those
cells once the run ends, so analyzers on separate xdist workers do not overwrite one another.
"""

import functools
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

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

from requirements_tree import items, parents


@pytest.fixture
def claimed_runs(request: pytest.FixtureRequest) -> Callable[[str], dict[str, CaseResults]]:
    """A lookup of the active session's results for the mission tests that judge a rung.

    A recorded test judges a rung when its mission lists the rung, its scenario links to the rung,
    and its FSW claims a capability the rung belongs to. The test is found by importing it from the
    node ID in its `planned.json`. A mission listing the rung whose FSW claims none of the rung's
    capabilities is noted in `lookup.notes`, for the verdict to report as not judged. A recorded
    test whose file no longer exists claims nothing.

    Args:
        request: the pytest request.

    Returns:
        A function mapping an SRS ID to each judging test's results by node ID.
    """
    session = session_directory(request.config)
    rootpath = Path(request.config.rootpath)

    @functools.cache
    def module(file: str) -> ModuleType:
        """Import a test file once, under a name of its own.

        Args:
            file: the file, relative to the rootdir.

        Returns:
            The module.
        """
        path = rootpath / file
        name = f"_monte_carlo_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        imported = importlib.util.module_from_spec(spec)
        sys.modules[name] = imported
        spec.loader.exec_module(imported)
        return imported

    @functools.cache
    def lookup(requirement_id: str) -> dict[str, CaseResults]:
        """Each judging test's results by node ID.

        Args:
            requirement_id: the SRS ID.

        Returns:
            The results by node ID.
        """
        capabilities = set(parents(items("SRS")[requirement_id]))
        found, notes = {}, []
        for recorded in recorded_tests(session):
            file, *names = recorded.nodeid.split("::")
            if not (rootpath / file).is_file():
                continue
            test = module(file)
            for name in names:
                test = getattr(test, name, None)
            mission = getattr(test, "mission", None)
            if mission is None or requirement_id not in mission.rungs:
                continue
            if requirement_id not in parents(items("TST")[test.scenario_id]):
                continue
            if not capabilities & set(mission.fsw.provides):
                claims = list(mission.fsw.provides)
                notes.append(
                    f"{recorded.nodeid}: {mission.fsw.__name__} claims {claims},"
                    f" none of this rung's {sorted(capabilities)}"
                )
                continue
            found[recorded.nodeid] = read_test_results(recorded.directory)
        lookup.notes[requirement_id] = notes
        return found

    lookup.notes = {}
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
) -> Callable[..., None]:
    """Judge a requirement from its analyzer's number for each run, and write its report.

    Args:
        request: the pytest request.
        claimed_runs: the results of the tests claiming an ID.
        allowed_failures: the allowed-failures rule.

    Returns:
        `judge(requirement_id, numbers, figures, *, x, p, c)`, where `numbers` holds each claiming
        test's number by case. A case fails when it crashed or its number is not at most `x`, NaN
        included.
    """
    session = Path(session_directory(request.config))
    report = session / "report"

    def judge(
        requirement_id: str,
        numbers: dict[str, dict[int, float]],
        figures: dict[str, Figure],
        *,
        x: float,
        p: float,
        c: float,
    ) -> None:
        """Give each claiming test a cell, write the report, then fail or skip unless all pass.

        A test's cell is not judged when a planned case has neither a run nor a crash record, or
        when no failure count shows `p` at `c`; it fails when more cases fail than are allowed.

        Args:
            requirement_id: the requirement.
            numbers: each claiming test's number by case.
            figures: each claiming test's plot, saved as `<ID>.png` under the report's copy
                of the test's folder in the session.
            x: the largest number a passing run may have.
            p: the share of runs that must pass.
            c: the confidence the demonstration demands.
        """
        claimed = claimed_runs(requirement_id)
        folders = {test.nodeid: test.directory for test in recorded_tests(session)}
        failing, unjudged = [], []
        for nodeid, results in claimed.items():
            failed = sorted(
                [case for case, number in numbers[nodeid].items() if not number <= x]
                + list(results.crashes)
            )
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
            folder = report / folders[nodeid].relative_to(session)
            folder.mkdir(parents=True, exist_ok=True)
            figures[nodeid].savefig(folder / f"{requirement_id}.png")
            record = {
                "requirement": requirement_id,
                "verdict": cell,
                "failed": len(failed),
                "found": len(results.runs) + len(results.crashes),
                "planned": results.planned,
                "allowed": allowed,
                "failed_cases": ", ".join(
                    f"{case} (crash)" if case in results.crashes else str(case) for case in failed
                ),
            }
            (folder / f"{requirement_id}.json").write_text(json.dumps(record))
        unjudged += claimed_runs.notes.get(requirement_id, [])
        if failing:
            pytest.fail(f"{requirement_id} failed\n" + "\n".join(failing))
        if unjudged:
            pytest.skip(f"{requirement_id} not judged: " + "; ".join(unjudged))
        if not claimed and not unjudged:
            pytest.skip(f"{requirement_id} not judged: no test claims it")

    return judge


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Write each test's `matrix.md` and the report's rollup from the cells the analyzers wrote.

    A test's matrix lists each requirement it claims. The rollup is requirement by test, ending
    with each requirement's verdict: fail if any cell fails, else not judged if any cell is not
    judged, else pass. Nothing is written on an xdist worker or when no session is active.

    Args:
        session: the pytest session.
    """
    if hasattr(session.config, "workerinput"):
        return
    try:
        report = Path(session_directory(session.config)) / "report"
    except NoSessionError:
        return
    cells = {
        (path.parent.relative_to(report).as_posix(), path.stem): json.loads(path.read_text())
        for path in sorted(report.rglob("*.json"))
    }
    if not cells:
        return
    tests = sorted({test for test, _ in cells})
    requirements = sorted({requirement for _, requirement in cells})
    for test in tests:
        rows = [
            "| Requirement | Verdict | Failed/Found/Planned | Allowed | Failed cases |",
            "|---|---|---|---|---|",
        ]
        for requirement in requirements:
            if cell := cells.get((test, requirement)):
                rows.append(
                    f"| {requirement} | {cell['verdict']} | {cell['failed']}/{cell['found']}/"
                    f"{cell['planned']} | {cell['allowed']} | {cell['failed_cases']} |"
                )
        (report / test / "matrix.md").write_text("\n".join(rows) + "\n")
    links = [f"[{'/'.join(test.split('/')[-3:])}]({test}/matrix.md)" for test in tests]
    rows = [f"| Requirement | {' | '.join(links)} | Verdict |", "|---" * (len(tests) + 2) + "|"]
    for requirement in requirements:
        row = [cells.get((test, requirement)) for test in tests]
        verdicts = {cell["verdict"] for cell in row if cell}
        overall = next(v for v in ("fail", "not judged", "pass") if v in verdicts)
        shown = []
        for test, cell in zip(tests, row, strict=True):
            if cell is None:
                shown.append("—")
                continue
            text = cell["verdict"]
            if text != "not judged":
                text += f", {cell['failed']} of {cell['allowed']} allowed"
            shown.append(f"[{text}]({test}/{requirement}.png)")
        rows.append(f"| {requirement} | {' | '.join(shown)} | {overall} |")
    (report / "matrix.md").write_text("\n".join(rows) + "\n")
