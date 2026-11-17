"""Judge the active session from a notebook cell, and show the result there.

`judge()` runs the requirement analyzers in a subprocess, as `just judge` does, prints why any
rung failed or was not judged and which folders it skipped, then shows one row per rung and one
column per flight. `judge()` raises when an analyzer errors rather than failing its rung.
`plots(<SRS ID>)` shows that rung's plot for each flight. `run_notebook` executes a notebook end to
end in a kernel, as the test suite does.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
from IPython.display import Image, display
from jupyter_client.kernelspec import KernelSpecManager
from wise_dynamics.sessions import current_session

from harness import requirements_tree
from harness.judging import skipped_folders

KERNEL = "wise-gnc-design"

_EXECUTE = """
import sys
from pathlib import Path

import jupytext
import nbformat
from jupytext.kernels import kernelspec_from_language
from nbclient import NotebookClient
from traitlets.config import Config

path, out, ip = sys.argv[1:]
notebook = jupytext.read(path)
if not notebook.metadata.get("kernelspec", {}).get("name"):
    language = notebook.metadata["jupytext"]["main_language"]
    notebook.metadata["kernelspec"] = kernelspec_from_language(language)
config = Config({"KernelManager": {"transport": "ipc", "ip": ip}})
resources = {"metadata": {"path": str(Path(path).parent)}}
NotebookClient(notebook, timeout=None, resources=resources, config=config).execute()
nbformat.write(notebook, out)
"""
"""Executes a percent-format notebook in its folder, as `jupytext --execute` does, in the kernel
jupytext picks for its language, over IPC sockets at a path prefix given: `<notebook> <executed
copy> <socket prefix>`."""


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


def _errored(report: Path) -> list[str]:
    """Each analyzer that errored rather than failing its rung, from the run's JUnit report.

    A failing rung is the judging plugin's `pytest.fail` of `<rung> failed` in the test judging
    that rung; any other failure, or an error, is the analyzer's.

    Args:
        report: the JUnit XML report the analyzers' run wrote.

    Returns:
        Each such test, as its pytest node ID `<file>::<test>`, with its error's first line.
    """
    errored = []
    for case in ET.parse(report).iter("testcase"):
        test = f"{case.get('classname', '').replace('.', '/')}.py::{case.get('name')}"
        rung = re.search(r"\[(.+)\]$", case.get("name", ""))
        for outcome in case:
            message = (outcome.get("message") or "").splitlines()
            first = message[0] if message else outcome.tag
            if outcome.tag == "failure" and rung and first == f"Failed: {rung.group(1)} failed":
                continue
            if outcome.tag in ("failure", "error"):
                errored.append(f"- {test}: {first}")
    return errored


def judge() -> pd.DataFrame:
    """Judge the active session and return the matrix: a row per rung, a column per flight.

    A cell reads `pass`, `fail` or `not judged`, with the failed cases out of the allowed ones.

    Returns:
        The matrix.

    Raises:
        RuntimeError: pytest failed for a reason other than a failing or unjudged rung: it could
            not run the analyzers, or an analyzer errored rather than failing its rung, naming
            each such analyzer and its error.
    """
    with tempfile.TemporaryDirectory() as directory:
        report = Path(directory) / "judging.xml"
        command = [sys.executable, "-m", "pytest", "analysis", "-q", "-rfEs"]
        command += ["-p", "no:cacheprovider", f"--junitxml={report}"]
        result = subprocess.run(
            command, cwd=requirements_tree.ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode not in (0, 1, 5):
            out = f"{result.stdout}{result.stderr}"
            raise RuntimeError(f"judging failed ({result.returncode}):\n{out}")
        errored = _errored(report)
    if errored:
        errors = "\n".join(errored)
        raise RuntimeError(f"analyzers errored rather than judging:\n{errors}\n{result.stdout}")
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
    sockets in that directory, not TCP ports, which kernels started at once can race to bind. The
    executed copy goes to that directory too, never beside the notebook. Cells that only the
    notebook runs, such as those that judge and plot, run too.

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
        addopts = f"{os.environ.get('PYTEST_ADDOPTS', '')} -o sim_out={sessions}"
        result = subprocess.run(
            [sys.executable, "-c", _EXECUTE, str(path), f"{tmp}/run.ipynb", f"{tmp}/kernel"],
            env={
                **os.environ,
                "JPY_SESSION_NAME": str(path),
                "WISE_DYNAMICS_CAPPED": "1",
                "PYTEST_ADDOPTS": addopts,
            },
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"{path.name} failed:\n{result.stderr}")
