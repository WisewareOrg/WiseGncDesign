"""Skips this tier when WiseDynamics is not installed, and fails the session instead when
`REQUIRE_SIM=1`."""

import os

import pytest

if os.environ.get("REQUIRE_SIM") == "1":
    import wise_dynamics  # noqa: F401
else:
    pytest.importorskip("wise_dynamics")
