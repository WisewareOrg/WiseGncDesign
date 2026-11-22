"""Judge the active session from a notebook cell, and show the result there.

`judge()` runs the requirement analyzers in a subprocess, as `just judge` does, prints why any
rung failed or was not judged and which folders it skipped, then shows one row per rung and one
column per flight.
`plots(<SRS ID>)` shows that rung's plot for each flight. `run_notebook` executes a notebook end to
end in a kernel, as the test suite does.
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import jupytext
import pandas as pd
from IPython.display import Image, display
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError
from traitlets.config import Config
from wise_dynamics.sessions import current_session

from harness import requirements_tree
from harness.judging import skipped_folders

KERNEL = "wise-gnc-design"


def _report() -> Path:
    """The active session's report directory.

    Returns:
        `report` in the session `current_session()` finds.
    """
    return current_session() / "report"


def _cells() -> dict[tuple[str, str], dict]:
    """Every cell the last judging wrote, by flight and rung.

    Returns:
        Each cell's record by (flight, SRS ID); a flight is `<notebook>/<class>/<test>`.
    """
    report = _report()
    return {
        ("/".join(path.parent.relative_to(report).parts[-3:]), path.stem): json.loads(
            path.read_text()
        )
        for path in sorted(report.rglob("SRS*.json"))
    }


def judge() -> pd.DataFrame:
    """Judge the active session and return the matrix: a row per rung, a column per flight.

    A cell reads `pass`, `fail` or `not judged`, with the failed cases out of the allowed ones.

    Returns:
        The matrix.

    Raises:
        RuntimeError: pytest failed for a reason other than a failing or unjudged rung.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "analysis", "-q", "-rfEs", "-p", "no:cacheprovider"],
        cwd=requirements_tree.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1, 5):
        raise RuntimeError(f"judging failed ({result.returncode}):\n{result.stdout}{result.stderr}")
    summary = result.stdout.partition("short test summary info")[2].splitlines()[1:]
    print("\n".join(summary) if summary else result.stdout.strip() or result.stderr)
    skipped = skipped_folders(current_session(), requirements_tree.ROOT)
    if skipped:
        print("Skipped folders:")
        print("\n".join(f"- {folder}: {reason}" for folder, reason in sorted(skipped.items())))
    headers = {uid: item["header"].strip() for uid, item in requirements_tree.items("SRS").items()}
    rows: dict[str, dict[str, str]] = {}
    for (flight, uid), cell in _cells().items():
        text = cell["verdict"]
        if text != "not judged":
            text += f" {cell['failed']}/{cell['allowed']}"
        notebook, vehicle, test = flight.split("/")
        column = f"{notebook}: {vehicle.removeprefix('Test_')} / {test.removeprefix('test_')}"
        rows.setdefault(f"{uid} {headers.get(uid, '')}", {})[column] = text
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def plots(requirement_id: str) -> None:
    """Show one rung's plot for each flight the last judging wrote.

    Args:
        requirement_id: the SRS ID.
    """
    for path in sorted(_report().rglob(f"{requirement_id}.png")):
        print("/".join(path.parent.parts[-3:]))
        display(Image(filename=path))


def run_notebook(path: Path) -> None:
    """Execute a notebook end to end in the `wise-gnc-design` kernel, capped at two cases a flight.

    The kernel runs in the notebook's folder, as in Lab, so the session it finds is the one its
    flights land in. Its sessions are kept in a temporary directory of the run's own, the `sim_out`
    every pytest the run starts takes through `PYTEST_ADDOPTS`, so two runs at once, or one run
    and the project's own sessions, never fly or judge in one session. The kernel listens on IPC
    sockets in that directory, not TCP ports, which kernels started at once can race to bind.
    Nothing is written beside the notebook. Cells that only the notebook runs, such as those that
    judge and plot, run too.

    Args:
        path: the notebook's percent-format file.

    Raises:
        RuntimeError: the kernel is not registered, or a cell raised.
    """
    if KERNEL not in KernelSpecManager().find_kernel_specs():
        raise RuntimeError(
            f"the {KERNEL} kernel is not registered; run `just local` or `just pinned`"
        )
    with tempfile.TemporaryDirectory() as tmp:
        sessions = shlex.quote(f"{tmp}/sessions")
        client = NotebookClient(
            jupytext.read(path),
            timeout=None,
            kernel_name=KERNEL,
            resources={"metadata": {"path": str(path.parent)}},
            config=Config({"KernelManager": {"transport": "ipc", "ip": f"{tmp}/kernel"}}),
        )
        env = {
            **os.environ,
            "JPY_SESSION_NAME": str(path),
            "WISE_DYNAMICS_CAPPED": "1",
            "PYTEST_ADDOPTS": f"{os.environ.get('PYTEST_ADDOPTS', '')} -o sim_out={sessions}",
        }
        try:
            client.execute(env=env)
        except CellExecutionError as error:
            raise RuntimeError(f"{path.name} failed:\n{error}") from error
