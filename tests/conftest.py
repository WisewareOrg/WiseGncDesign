"""The campaign check: at the end of a session that ran scenario cases, the run files those
cases recorded share one directory, which is `--sim-out` when that option was given; they are
exactly the `run_*.h5` files in it; and that directory loads through
`gnc_analysis.runs.load_campaign`.

Each scenario case records its run file with `record_property("run_file", path)`. These hooks
live in this file because the pytest-xdist controller loads it for every session under
`tests/`.
"""

from pathlib import Path

import pytest

_recorded: set[Path] = set()
_report: list[str] = []
_failed = False


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Collects the run file of every scenario case that reached its call phase."""
    if report.when == "call" and not report.skipped:
        _recorded.update(
            Path(value) for name, value in report.user_properties if name == "run_file"
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """On the controller, checks the campaign directory against the recorded run files."""
    global _failed
    if hasattr(session.config, "workerinput") or not _recorded:
        return
    from gnc_analysis.runs import RunDataError, load_campaign

    recorded = {p.resolve() for p in _recorded}
    directories = sorted({p.parent for p in recorded})
    problems: list[str] = []
    if len(directories) > 1:
        problems.append(f"run files written to {len(directories)} directories: {directories}")
    else:
        out_dir = directories[0]
        requested = session.config.getoption("--sim-out", default=None)
        if requested and Path(requested).resolve() != out_dir:
            problems.append(f"run files written to {out_dir}, not to --sim-out {requested}")
        present = {p.resolve() for p in out_dir.glob("run_*.h5")}
        problems += [f"recorded but absent from {out_dir}: {p}" for p in sorted(recorded - present)]
        problems += [
            f"present in {out_dir} but written by no case: {p}" for p in sorted(present - recorded)
        ]
    if not problems:
        try:
            load_campaign(out_dir)
        except RunDataError as exc:
            problems.append(str(exc))

    if problems:
        _failed = True
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        _report.extend(f"FAILED: {problem}" for problem in problems)
    else:
        _report.append(f"campaign check: {len(recorded)} runs loaded from {out_dir}")


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    """Reports the campaign check's outcome in its own summary section."""
    if _report:
        terminalreporter.section("campaign check", red=_failed, green=not _failed)
        for line in _report:
            terminalreporter.write_line(line)
