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
        raise RuntimeError("analyzers errored rather than judging:\n" + "\n".join(errored))
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
    flights land in. The executed copy goes to a temporary directory, never beside the notebook.
    Cells that only the notebook runs, such as those that judge and plot, run too.

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
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jupytext",
                "--execute",
                "--run-path",
                str(path.parent),
                str(path),
                "-o",
                f"{tmp}/run.ipynb",
            ],
            env={**os.environ, "JPY_SESSION_NAME": str(path), "WISE_DYNAMICS_CAPPED": "1"},
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"{path.name} failed:\n{result.stderr}")
