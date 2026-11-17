"""The notebook runner fails on an error in any cell, notebook-only cells included."""

from pathlib import Path

import pytest
from jupyter_client.kernelspec import KernelSpecManager

from harness.notebook import run_notebook

CELLS = """\
# %%
x = 1

# %% active="ipynb"
# {body}
"""


def test_an_error_in_a_notebook_only_cell_fails_the_run(tmp_path: Path) -> None:
    """The seeded error: a notebook-only cell that raises fails the run.

    Args:
        tmp_path: the test's directory.
    """
    notebook = tmp_path / "seeded.py"
    notebook.write_text(CELLS.format(body='raise RuntimeError("seeded")'))

    with pytest.raises(RuntimeError, match="seeded"):
        run_notebook(notebook)


def test_each_run_finds_a_session_of_its_own_outside_the_notebook_s_folder(tmp_path: Path) -> None:
    """Two notebooks in one folder find two sessions, neither the folder's own `monte_carlo`.

    So one notebook test's flights and judging never see another's, however the tests are run.

    Args:
        tmp_path: the notebooks' folder.
    """
    for name in ("first", "second"):
        notebook = tmp_path / f"{name}.py"
        body = (
            "from pathlib import Path; from wise_dynamics.sessions import current_session; "
            f'Path(r"{tmp_path}/{name}.session").write_text(str(current_session()))'
        )
        notebook.write_text(CELLS.format(body=body))
        run_notebook(notebook)

    first, second = (Path((tmp_path / f"{n}.session").read_text()) for n in ("first", "second"))
    assert first != second
    for session in (first, second):
        assert not session.is_relative_to(tmp_path), session


def test_each_run_s_kernel_listens_on_files_of_its_own_not_tcp_ports(tmp_path: Path) -> None:
    """The kernel talks over IPC sockets of the run's own, never TCP ports kernels race for.

    Args:
        tmp_path: the notebook's folder.
    """
    notebook = tmp_path / "transport.py"
    body = (
        "from ipykernel.connect import get_connection_info; "
        "info = get_connection_info(unpack=True); "
        'assert info["transport"] == "ipc", info["transport"]; '
        f'assert not info["ip"].startswith(r"{tmp_path}"), info["ip"]'
    )
    notebook.write_text(CELLS.format(body=body))

    run_notebook(notebook)


def test_the_run_is_capped_and_names_the_notebook_as_its_session(tmp_path: Path) -> None:
    """The kernel sees the cap and the notebook's path, so a run cannot fly the full campaign.

    It runs in the notebook's folder, as in Lab, so it finds the session the notebook's flights
    land in; the executed copy is written elsewhere. Its notebook-only cell holds, so it is also
    the control for the seeded error: a notebook whose cells all run passes.

    Args:
        tmp_path: the test's directory.
    """
    notebook = tmp_path / "env.py"
    body = (
        'import os; assert os.environ["WISE_DYNAMICS_CAPPED"] == "1"; '
        f'assert os.environ["JPY_SESSION_NAME"] == r"{notebook}"; '
        f'assert os.getcwd() == r"{tmp_path}"'
    )
    notebook.write_text(CELLS.format(body=body))

    run_notebook(notebook)

    assert [path.name for path in tmp_path.iterdir()] == ["env.py"]


def test_an_unregistered_kernel_fails_the_run_naming_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `wise-gnc-design` kernel the run refuses before executing, and says how to register.

    Args:
        tmp_path: the test's directory.
        monkeypatch: the monkeypatch fixture.
    """
    monkeypatch.setattr(KernelSpecManager, "find_kernel_specs", lambda self: {})
    notebook = tmp_path / "ok.py"
    notebook.write_text(CELLS.format(body="assert x == 1"))

    with pytest.raises(RuntimeError, match=r"wise-gnc-design kernel is not registered.*just local"):
        run_notebook(notebook)
