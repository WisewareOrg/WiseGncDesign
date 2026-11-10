"""Requirement analysis: how many failed runs a requirement allows, and the metrics it judges.

A run is one run file as `error_bounds.read_run` returns it.
"""

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

import numpy as np
from scipy.stats import beta
from wise_dynamics.sessions import CaseResults

from gnc_analysis.error_bounds import attitude_error_rad, read_run

__all__ = ["Cell", "allowed_failures", "claimed_ids", "judge_cell", "worst_attitude_error_rad"]


def allowed_failures(n: int, p: float, c: float) -> int | None:
    """The most failed runs out of `n` that still show reliability `p` at confidence `c`.

    The failure rate's one-sided Clopper-Pearson upper bound at confidence `c` must stay within
    `1 - p`.

    Args:
        n: the number of runs.
        p: the reliability the requirement demands, the share of runs that pass.
        c: the confidence the demonstration demands.

    Returns:
        The largest failure count `k` whose upper bound is within `1 - p`, or None when even zero
        failures cannot show `p` at `c` with `n` runs.
    """
    k = 0
    while k < n and beta.ppf(c, k + 1, n - k) <= 1.0 - p:
        k += 1
    return k - 1 if k > 0 else None


def worst_attitude_error_rad(run: Mapping[str, np.ndarray]) -> float:
    """The largest attitude error of the estimate against truth over a run.

    Args:
        run: one run, holding `truth/sigma_BN` and `est/sigma_BN`.

    Returns:
        The largest error over the samples, in rad.
    """
    return float(np.max(attitude_error_rad(run["truth/sigma_BN"], run["est/sigma_BN"])))


def claimed_ids(rootpath: Path, nodeid: str) -> set[str]:
    """The requirement IDs a test claims with `verifies` marks on its module, class or function.

    Args:
        rootpath: the project root the node ID is relative to.
        nodeid: the test's node ID, `<file>::<class>::<function>`.

    Returns:
        The IDs.
    """
    file, *names = nodeid.split("::")
    path = rootpath / file
    name = f"_monte_carlo_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    chain = [module]
    for attribute in names:
        chain.append(getattr(chain[-1], attribute))
    ids: set[str] = set()
    for node in chain:
        marks = getattr(node, "pytestmark", [])
        for mark in marks if isinstance(marks, list) else [marks]:
            if mark.name == "verifies":
                ids.update(mark.args)
    return ids


class Cell(NamedTuple):
    """One claiming test judged against a requirement.

    Attributes:
        verdict: "pass", "fail" or "not judged".
        failed: the failed case numbers.
        found: the number of cases with a run or a crash record.
        planned: the number of planned cases.
        allowed: the allowed failures, or None.
        errors: the worst error of each run found, in rad.
        reason: why the cell is not judged, else empty.
    """

    verdict: str
    failed: list[int]
    found: int
    planned: int
    allowed: int | None
    errors: list[float]
    reason: str


def judge_cell(results: CaseResults, threshold: float, p: float, c: float) -> Cell:
    """Judge a test's cases 0..planned-1 against a worst-attitude-error threshold.

    A run fails when its worst error exceeds `threshold`, and a crash record is a failed case. The
    cell is not judged when a case has neither or no failure count shows `p` at `c`.

    Args:
        results: the test's planned count, run files and crash records.
        threshold: `X`, the largest worst error a passing run may have, in rad.
        p: the reliability the requirement demands.
        c: the confidence the demonstration demands.

    Returns:
        The cell.
    """
    failed, errors = [], []
    for case in range(results.planned):
        if case in results.runs:
            errors.append(worst_attitude_error_rad(read_run(results.runs[case])))
            if errors[-1] > threshold:
                failed.append(case)
        elif case in results.crashes:
            failed.append(case)
    found = sum(case in results.runs or case in results.crashes for case in range(results.planned))
    allowed = allowed_failures(results.planned, p, c)
    reason = ""
    if found < results.planned:
        reason = f"{results.planned - found} of {results.planned} cases have no result"
    elif allowed is None:
        reason = f"{results.planned} cases cannot show p={p} at c={c}"
    verdict = "not judged" if reason else "pass" if len(failed) <= allowed else "fail"
    return Cell(verdict, failed, found, results.planned, allowed, errors, reason)
