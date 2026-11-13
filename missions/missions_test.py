"""The mission notebooks run end to end, capped, in a kernel."""

from pathlib import Path

import pytest

from harness.notebook import run_notebook

NOTEBOOKS = sorted(
    path for path in Path(__file__).parent.glob("*.py") if not path.name.endswith("_test.py")
)
assert NOTEBOOKS, "no mission notebooks found beside this file"


@pytest.mark.xdist_group("notebooks")
@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda path: path.stem)
def test_a_mission_notebook_runs_end_to_end(notebook: Path) -> None:
    """Every cell runs, the notebook-only cells that judge and plot included.

    A notebook that flies the F´ host is skipped when the F´ build is absent.

    Args:
        notebook: the mission notebook's percent-format file.
    """
    if "gnc_cdh.fprime" in notebook.read_text():
        pytest.importorskip(
            "gnc_cdh.fprime._wise_fsw", reason="the F´ build is absent; run `just fsw`"
        )
    run_notebook(notebook)
