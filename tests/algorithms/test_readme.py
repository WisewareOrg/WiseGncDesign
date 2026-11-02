"""The worked example in `algorithms/README.md`, run as a doctest."""

import doctest
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "algorithms" / "README.md"


def test_the_readme_example_runs_as_written():
    result = doctest.testfile(str(README), module_relative=False, verbose=False)

    assert result.failed == 0
    assert result.attempted >= 9
