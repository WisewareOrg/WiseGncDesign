"""Judge a Monte Carlo session against the requirements its tests claim with `verifies` marks.

An analyzer module declares `REQUIREMENT` and two tests, one taking `session_run` and one taking
`requirement_verdict`. Each (requirement, claiming test) pair is a cell. `session_run` is one item
per case of a cell, `requirement_verdict` the requirement as a whole, and `report/matrix.md` in the
session records every cell.
"""

import importlib.util
import sys
import warnings
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from wise_dynamics.sessions import read_test_results, session_directory

from gnc_analysis.judging import (
    NOT_APPLICABLE,
    Cell,
    Judging,
    MonteCarloTest,
    RequirementVerdict,
    SessionRun,
    join_cases,
)

HEADER = [
    "Requirement", "Test", "Verdict", "Failed", "Found", "Planned", "Allowed",
    "Failing cases", "Crashed cases",
]  # fmt: skip


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
        sys.modules.pop(name, None)
        raise ImportError(f"cannot import the Monte Carlo test file {path}: {error!r}") from error
    return module


def _locate(config: pytest.Config, parts: tuple[str, ...]) -> tuple[Path, tuple[str, ...]] | None:
    """Find the test file and the names within it that a test folder stands for.

    Args:
        config: the pytest configuration.
        parts: the folder's path under the session.

    Returns:
        The file, then the enclosing classes and the function, or None when no file matches.
    """
    for split in range(len(parts) - 1, 0, -1):
        file = config.rootpath.joinpath(*parts[: split - 1], parts[split - 1] + ".py")
        if file.is_file():
            return file, parts[split:]
    return None


def _discover(config: pytest.Config) -> Judging:
    """Find the active session's tagged Monte Carlo tests.

    A folder whose test does not exist is listed in a warning and not judged. A test with no
    `verifies` mark is not judged.

    Args:
        config: the pytest configuration.

    Returns:
        The session's judging state.
    """
    session = session_directory(config)
    tests, vanished = [], []
    modules: dict[Path, ModuleType] = {}
    for planned in sorted(session.rglob("planned.json")):
        directory = planned.parent
        parts = directory.relative_to(session).parts
        located = _locate(config, parts)
        if located is None:
            vanished.append(str(directory.relative_to(session)))
            continue
        file, names = located
        if file not in modules:
            modules[file] = _import(file)
        chain = [modules[file]]
        for name in names:
            chain.append(getattr(chain[-1], name, None))
        if chain[-1] is None:
            vanished.append(str(directory.relative_to(session)))
            continue
        ids = _verifies(chain, "/".join(parts))
        if ids:
            relative = file.relative_to(config.rootpath)
            tests.append(
                MonteCarloTest(directory, relative, names, ids, read_test_results(directory))
            )
    if vanished:
        warnings.warn(
            f"session folders whose Monte Carlo test does not exist, not judged: {vanished}",
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
    claimers = judging.claimers(requirement)
    for test in claimers:
        results = test.results
        for case in sorted(set(results.runs) | set(results.crashes)):
            params.append((test, case))
            ids.append(f"{test.label}-{case}")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"two Monte Carlo tests give the same item id: {duplicates}")
    if not claimers:
        params, ids = [None], ["no-claim"]
    metafunc.parametrize("session_run", params, indirect=True, ids=ids)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Stop the run when a `verifies` ID is declared by no collected analyzer.

    Args:
        config: the pytest configuration.
        items: the collected items.

    Raises:
        pytest.UsageError: a `verifies` mark names a requirement that no analyzer declares.
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
        raise pytest.UsageError(
            f"verifies marks name requirements that no analyzer declares: {unknown}"
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


def _row(cell: Cell) -> list[str]:
    """One matrix row.

    Args:
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
        cell.requirement.id,
        cell.test.label,
        verdict,
        str(len(cell.failures)),
        str(cell.found),
        str(results.planned),
        allowed,
        join_cases(cell.failures),
        join_cases(cell.crashed),
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
            row = _row(judging.cell(requirement, test))
            lines.append("| " + " | ".join(row) + " |")
    report = judging.session / "report"
    report.mkdir(parents=True, exist_ok=True)
    (report / "matrix.md").write_text("\n".join(lines) + "\n")
