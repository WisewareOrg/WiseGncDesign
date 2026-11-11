"""Judge the active session from a notebook cell, and show the result there.

`judge()` runs the requirement analyzers in a subprocess, as `just judge` does, then shows one row
per rung and one column per flight. `plots(<SRS ID>)` shows that rung's plot for each flight.
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from IPython.display import Image, display
from wise_dynamics.sessions import read_pointer

from requirements_tree import ROOT, items


def _report() -> Path:
    """The active session's report directory.

    Returns:
        `monte_carlo/<session>/report`.
    """
    root = ROOT / "monte_carlo"
    return root / read_pointer(root) / "report"


def _cells() -> dict[tuple[str, str], dict]:
    """Every cell the last judging wrote, by flight and rung.

    Returns:
        Each cell's record by (flight, SRS ID); a flight is `<class>/<test>`.
    """
    report = _report()
    return {
        ("/".join(path.parent.relative_to(report).parts[-2:]), path.stem): json.loads(
            path.read_text()
        )
        for path in sorted(report.rglob("SRS*.json"))
    }


def judge() -> pd.DataFrame:
    """Judge the active session and return the matrix: a row per rung, a column per flight.

    A cell reads `pass`, `fail` or `not judged`, with the failed cases out of the allowed ones.

    Returns:
        The matrix.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "analysis", "-q", "-rs", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr)
    headers = {uid: item["header"].strip() for uid, item in items("SRS").items()}
    rows: dict[str, dict[str, str]] = {}
    for (flight, uid), cell in _cells().items():
        text = cell["verdict"]
        if text != "not judged":
            text += f" {cell['failed']}/{cell['allowed']}"
        vehicle, test = flight.split("/")
        column = f"{vehicle.removeprefix('Test_')} / {test.removeprefix('test_')}"
        rows.setdefault(f"{uid} {headers.get(uid, '')}", {})[column] = text
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def plots(requirement_id: str) -> None:
    """Show one rung's plot for each flight the last judging wrote.

    Args:
        requirement_id: the SRS ID.
    """
    for path in sorted(_report().rglob(f"{requirement_id}.png")):
        print("/".join(path.parent.parts[-2:]))
        display(Image(filename=path))
