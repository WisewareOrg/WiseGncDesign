"""The worked example in `cdh/README.md`, run as a doctest.

It boots the dead reckoner on a WiseDynamics spacecraft.
"""

import doctest
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "cdh" / "README.md"


def test_the_readme_example_runs_as_written():
    """Every example in `cdh/README.md` passes as a doctest, at least 10 of them."""
    result = doctest.testfile(str(README), module_relative=False, verbose=False)

    assert result.failed == 0
    assert result.attempted >= 10
