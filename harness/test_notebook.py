"""The notebook runner fails on an error in any cell, notebook-only cells included."""

from pathlib import Path

import pytest

CELLS = """\
# %%
x = 1

# %% active="ipynb"
# {body}
"""


@pytest.mark.xdist_group("notebooks")
def test_a_notebook_whose_cells_all_run_passes(tmp_path: Path) -> None:
    """The control: a notebook-only cell that holds passes the run.

    Args:
        tmp_path: the test's directory.
    """
    from harness.notebook import run_notebook

    notebook = tmp_path / "ok.py"
    notebook.write_text(CELLS.format(body="assert x == 1"))

    run_notebook(notebook)


@pytest.mark.xdist_group("notebooks")
def test_an_error_in_a_notebook_only_cell_fails_the_run(tmp_path: Path) -> None:
    """The seeded error: a notebook-only cell that raises fails the run.

    Args:
        tmp_path: the test's directory.
    """
    from harness.notebook import run_notebook

    notebook = tmp_path / "seeded.py"
    notebook.write_text(CELLS.format(body='raise RuntimeError("seeded")'))

    with pytest.raises(RuntimeError, match="seeded"):
        run_notebook(notebook)
