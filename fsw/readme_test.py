"""The worked example in `fsw/README.md`, run as a doctest.

It boots the dead reckoner on a WiseDynamics spacecraft.
"""

import doctest
from pathlib import Path

README = Path(__file__).with_name("README.md")


def test_the_readme_example_runs_as_written():
    """Every example in `fsw/README.md` passes as a doctest, and it has at least one."""
    result = doctest.testfile(str(README), module_relative=False, verbose=False)

    assert result.failed == 0
    assert result.attempted >= 1
