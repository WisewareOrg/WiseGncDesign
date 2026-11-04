"""Skips this tier when WiseDynamics is not installed.

With `REQUIRE_SIM=1` a missing WiseDynamics fails the session instead.
"""

import os

import pytest

if os.environ.get("REQUIRE_SIM") == "1":
    import wise_dynamics  # noqa: F401
else:
    pytest.importorskip("wise_dynamics")
