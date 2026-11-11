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


@pytest.mark.xdist_group("notebooks")
def test_the_run_is_capped_and_names_the_notebook_as_its_session(tmp_path: Path) -> None:
    """The kernel sees the cap and the notebook's path, so a run cannot fly the full campaign.

    Args:
        tmp_path: the test's directory.
    """
    from harness.notebook import run_notebook

    notebook = tmp_path / "env.py"
    body = (
        'import os; assert os.environ["WISE_DYNAMICS_CAPPED"] == "1"; '
        f'assert os.environ["JPY_SESSION_NAME"] == r"{notebook}"'
    )
    notebook.write_text(CELLS.format(body=body))

    run_notebook(notebook)


def test_an_unregistered_kernel_fails_the_run_naming_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `wise-gnc-design` kernel the run refuses before executing, and says how to register.

    Args:
        tmp_path: the test's directory.
        monkeypatch: the monkeypatch fixture.
    """
    from jupyter_client.kernelspec import KernelSpecManager

    from harness.notebook import run_notebook

    monkeypatch.setattr(KernelSpecManager, "find_kernel_specs", lambda self: {})
    notebook = tmp_path / "ok.py"
    notebook.write_text(CELLS.format(body="assert x == 1"))

    with pytest.raises(RuntimeError, match=r"wise-gnc-design kernel is not registered.*just local"):
        run_notebook(notebook)
