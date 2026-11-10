"""The `claimed_runs` fixture, and the session report's matrix of every requirement's cells.

Each requirement analyzer writes its cells to `report/<ID>.md`; `matrix.md` gathers them once the
run ends, so analyzers on separate xdist workers do not overwrite one another.
"""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from wise_dynamics.sessions import (
    CaseResults,
    NoSessionError,
    read_test_results,
    recorded_tests,
    session_directory,
)


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
