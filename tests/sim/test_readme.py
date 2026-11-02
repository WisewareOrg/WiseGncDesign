"""The worked example in `cdh/README.md`, booting the dead reckoner against a WiseDynamics
plant, run as a doctest."""

import doctest
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "cdh" / "README.md"


def test_the_readme_example_runs_as_written():
    result = doctest.testfile(str(README), module_relative=False, verbose=False)

    assert result.failed == 0
    assert result.attempted >= 10
