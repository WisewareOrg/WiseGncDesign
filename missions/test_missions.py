"""The mission notebooks run end to end, capped, in a kernel."""

from pathlib import Path

import pytest

NOTEBOOKS = sorted(
    path for path in Path(__file__).parent.glob("*.py") if not path.name.startswith("test_")
)
assert NOTEBOOKS, "no mission notebooks found beside this file"


@pytest.mark.xdist_group("notebooks")
@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda path: path.stem)
def test_a_mission_notebook_runs_end_to_end(notebook: Path) -> None:
    """Every cell runs, the notebook-only cells that judge and plot included.

    Args:
        notebook: the mission notebook's percent-format file.
    """
    from harness.notebook import run_notebook

    run_notebook(notebook)
