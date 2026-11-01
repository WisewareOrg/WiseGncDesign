"""Validates the whole campaign directory against this repository's own analysis loader once
the session completes."""

import os

import pytest

# Both CI jobs that run tests/sim set REQUIRE_SIM=1: a missing sim/h5py there is a real failure
# (the bare import below raises ModuleNotFoundError, naming the module), not something to skip
# past. Locally, where the sim extra is optional and the unit tests never depend on it, a bare
# `pytest` run still collects and runs them cleanly via the skip below.
if os.environ.get("REQUIRE_SIM") == "1":
    import h5py  # noqa: F401
    import sim  # noqa: F401
else:
    pytest.importorskip("sim")
    pytest.importorskip("h5py")

# Set from pytest_runtest_logreport, not session.items: under pytest-xdist the controller
# process never collects test items itself (it only relays reports forwarded from workers), so
# session.items and pytest_collection_modifyitems are both empty there.
_ran_scenario_cases = False


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    global _ran_scenario_cases
    if report.nodeid.startswith("tests/sim/"):
        _ran_scenario_cases = True


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Checks every run file written into --sim-out against gnc_analysis.runs.load_campaign,
    once per session (the controlling process, not a pytest-xdist worker). Fails loudly, rather
    than returning silently, whenever this session actually ran scenario cases: a missing
    plugin attribute, or a run-file count that doesn't match --sim-runs (the outcome a worker
    writing into the wrong directory under -n would actually produce), are each a failure
    here."""
    config = session.config
    if hasattr(config, "workerinput"):
        return  # only the controller checks the campaign, once

    if not _ran_scenario_cases:
        return  # this session never touched the scenario suite

    if not hasattr(config, "_wise_dynamics_out_dir"):
        session.exitstatus = 1
        print(
            "tests/sim ran scenario cases, but the sim plugin's _wise_dynamics_out_dir "
            "attribute is missing; the plugin may have changed"
        )
        return
    out_dir = config._wise_dynamics_out_dir

    expected_runs = config.getoption("--sim-runs")
    actual_runs = sorted(out_dir.glob("run_*.h5"))
    if len(actual_runs) != expected_runs:
        session.exitstatus = 1
        print(f"expected {expected_runs} run files in {out_dir}, found {len(actual_runs)}")
        return

    from gnc_analysis.runs import RunDataError, load_campaign

    try:
        load_campaign(out_dir)
    except RunDataError as exc:
        session.exitstatus = 1
        print(f"campaign export failed gnc_analysis's loader: {exc}")
