"""Validates the whole campaign directory against this repository's own analysis loader once
the session completes (the root conftest.py loads WiseDynamics' pytest plugin itself)."""

import pytest


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Checks every run file written into --out against gnc_analysis.runs.load_campaign, once
    per session (the controlling process, not a pytest-xdist worker)."""
    config = session.config
    if hasattr(config, "workerinput"):
        return

    out_dir = getattr(config, "_wise_dynamics_out_dir", None)
    if out_dir is None or not any(out_dir.glob("run_*.h5")):
        return

    from gnc_analysis.runs import RunDataError, load_campaign

    try:
        load_campaign(out_dir)
    except RunDataError as exc:
        session.exitstatus = 1
        print(f"campaign export failed gnc_analysis's loader: {exc}")
