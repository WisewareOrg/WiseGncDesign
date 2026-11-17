"""Parity: the Python and F´ builds' flights of one configuration agree on what FPP declares.

See ADR 0004 rev 2, "Parity is an analyzer whose spec is a minimum". Its unit is a twin: one
flight on each build of the same vehicle, configuration and scenario, case `k` against case `k`.
Everything it compares is read from the contract, so an algorithm adds nothing here:

- the telemetry of every channel each algorithm member's component declares, where the members are
  the instances the configuration's rate groups run (`fsw.codegen.members`);
- the command log's entries for every command those components declare: time sent, name,
  arguments, response and response time.

The spec is a minimum, and nothing else is read: a command's free-text reason and context, F´'s
parameter set and save commands, any other component's command or channel, a channel the member
does not declare, and the case's parameter record. Both builds' records come from the same ground
code, so comparing them would prove nothing about what a build holds; each build's boot tests
check what it loads from the record.

Each tolerance has its reason:

- A finite float value of a channel agrees within `TOLERANCE` times the channel's largest finite
  magnitude in the Python build's case. Both builds evaluate the same double-precision math in
  different languages, so they may differ in the last bits; one scale per channel is unit-free and
  makes a row of zeros no stricter than the rest. A non-finite value agrees only with the same
  non-finite value in the same place, NaN with NaN and each infinity with itself, and never widens
  the scale.
- A command's float argument agrees by the same rules, scaled by that argument's largest finite
  magnitude over the command's entries in the Python log: a procedure may compute arguments from
  truth, which carries the builds' last-bit differences once a flight actuates.
- Every other value is exact: non-float telemetry, each write's time, every value's dtype and
  shape, and a command's time, name, response and response time. Both builds run the same FPP
  rates on the same tick, so times and responses have no source of last-bit difference.
- Units are not compared: both builds take them from the same FPP format string.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
from wise_dynamics.sessions import current_session, read_test_results, recorded_tests, run_path

from fsw.codegen.deployment import CONTRACT, Contract, configuration_model
from fsw.codegen.fpp_model import Component
from fsw.codegen.members import members
from harness import requirements_tree
from harness.judging import skipped_folders
from harness.runs import read_run

__all__ = ["TOLERANCE", "parity", "session_parity"]

TOLERANCE = 1e-12
"""A float value's largest disagreement, relative to its channel's or argument's magnitude."""

_COMMAND_FIELDS = ("t_s", "name", "response", "response_t_s")
"""A command entry's fields compared exactly; its arguments are compared by `_differ`."""


def _roles(gnc: str, contract: Contract) -> list[tuple[str, Component]]:
    """The configuration's algorithm members, each by its role: its instance's name, module dropped.

    Args:
        gnc: the configuration.
        contract: the contract holding it.

    Returns:
        Each member's role, such as `nav`, as the dictionary names it, with its component.
    """
    model = configuration_model(gnc, contract=contract)
    return [
        (instance.name.split(".", 1)[1], model.components[instance.component])
        for group in members(model, gnc).values()
        for instance in group
    ]


def _magnitude(values: np.ndarray) -> float:
    """The largest magnitude among float values' finite elements.

    Args:
        values: the values.

    Returns:
        The magnitude, 0 for values with none.
    """
    return float(np.max(np.abs(values), where=np.isfinite(values), initial=0.0))


def _differ(python: Any, fprime: Any, scale: float) -> str | None:
    """How a value of the F´ build differs from the Python build's, by the module's rules.

    Args:
        python: the Python build's value.
        fprime: the F´ build's value.
        scale: the magnitude a float disagreement is relative to.

    Returns:
        The difference, or None when they agree.
    """
    p, f = np.asarray(python), np.asarray(fprime)
    if p.dtype != f.dtype or p.shape != f.shape:
        return f"is {p.dtype} {p.shape} on python and {f.dtype} {f.shape} on fprime"
    if p.dtype.kind != "f":
        return None if np.array_equal(p, f) else "differs"
    finite = np.isfinite(p)
    same = np.isnan(p) & np.isnan(f) | (p == f)
    if np.any(finite != np.isfinite(f)) or np.any(~finite & ~same):
        return "is non-finite in different places or values"
    worst = _magnitude(np.subtract(f, p, out=np.zeros_like(p), where=finite))
    if worst > TOLERANCE * scale:
        return f"differs by {worst:.3e}, beyond {TOLERANCE:g} x {scale:.3e}"
    return None


def _telemetry(
    roles: list[tuple[str, Component]], python: dict[str, Any], fprime: dict[str, Any]
) -> list[str]:
    """How one case's declared channels disagree.

    Args:
        roles: the members, by role.
        python: the Python build's run, as `read_run` gives it.
        fprime: the F´ build's run.

    Returns:
        The problems.
    """
    problems = []
    for role, component in roles:
        for channel in component.channels:
            tlm, tlm_t = f"tlm/{role}.{channel.name}", f"tlm_t/{role}.{channel.name}"
            written = [
                build for build, run in (("python", python), ("fprime", fprime)) if tlm in run
            ]
            if len(written) == 1:
                problems.append(f"{tlm} is written by {written[0]} only")
            if len(written) < 2:
                continue
            p = python[tlm]
            scale = _magnitude(p) if p.dtype.kind == "f" else 0.0
            for name, difference in (
                (tlm, _differ(p, fprime[tlm], scale)),
                (tlm_t, _differ(python[tlm_t], fprime[tlm_t], 0.0)),
            ):
                if difference:
                    problems.append(f"{name} {difference}")
    return problems


def _commands(
    roles: list[tuple[str, Component]],
    python: list[dict[str, Any]],
    fprime: list[dict[str, Any]],
) -> list[str]:
    """How one case's logs of commands to the members disagree.

    Args:
        roles: the members, by role.
        python: the Python build's command log.
        fprime: the F´ build's command log.

    Returns:
        The problems.
    """
    declared = {f"{role}.{c.name}" for role, component in roles for c in component.commands}
    python = [entry for entry in python if entry["name"] in declared]
    fprime = [entry for entry in fprime if entry["name"] in declared]
    if len(python) != len(fprime):
        first = next(
            (
                i
                for i, (p, f) in enumerate(zip(python, fprime, strict=False))
                if p["name"] != f["name"]
            ),
            min(len(python), len(fprime)),
        )
        return [
            f"python sent {len(python)} contract commands and fprime {len(fprime)}; their names"
            f" first differ at entry {first}"
        ]
    scales: dict[tuple[str, str], float] = {}
    for entry in python:
        for argument, value in entry["args"].items():
            values = np.asarray(value)
            if values.dtype.kind == "f":
                key = (entry["name"], argument)
                scales[key] = max(scales.get(key, 0.0), _magnitude(values))
    problems = []
    for i, (p, f) in enumerate(zip(python, fprime, strict=True)):
        where = f"command {i} {p['name']}"
        problems.extend(
            f"{where}: {field} {p[field]!r} on python, {f[field]!r} on fprime"
            for field in _COMMAND_FIELDS
            if p[field] != f[field]
        )
        if p["args"].keys() != f["args"].keys():
            problems.append(f"{where}: arguments {sorted(p['args'])} and {sorted(f['args'])}")
            continue
        for argument, value in p["args"].items():
            scale = scales.get((p["name"], argument), 0.0)
            if difference := _differ(value, f["args"][argument], scale):
                problems.append(f"{where}: argument {argument} {difference}")
    return problems


def parity(gnc: str, python: Path, fprime: Path, *, contract: Contract = CONTRACT) -> list[str]:
    """Every way two flights of a configuration, one on each build, disagree.

    A differing planned count, a case with a run file on one side only and a case that crashed on
    either side are each a problem, and every case with a run file on both sides is compared. A
    run missing the write times of a channel it wrote is malformed and raises as reading it does.

    Args:
        gnc: the configuration both flew.
        python: the Python build's flight folder.
        fprime: the F´ build's flight folder.
        contract: the contract holding the configuration, the repository's by default.

    Returns:
        The problems, each naming its case and item; empty when the twins agree.
    """
    roles = _roles(gnc, contract)
    results = {"python": read_test_results(python), "fprime": read_test_results(fprime)}
    problems = []
    if results["python"].planned != results["fprime"].planned:
        problems.append(
            f"planned {results['python'].planned} cases on python and"
            f" {results['fprime'].planned} on fprime"
        )
    cases = {case for r in results.values() for case in (*r.runs, *r.crashes)}
    for case in sorted(cases):
        crashed = [build for build, r in results.items() if case in r.crashes]
        ran = [build for build, r in results.items() if case in r.runs]
        if crashed:
            problems.append(f"case {case}: crashed on {' and '.join(crashed)}")
            continue
        if len(ran) == 1:
            problems.append(f"case {case}: a run file on {ran[0]} only")
            continue
        p, f = read_run(run_path(python, case)), read_run(run_path(fprime, case))
        found = [
            *_telemetry(roles, p, f),
            *_commands(roles, json.loads(str(p["commands"])), json.loads(str(f["commands"]))),
        ]
        problems.extend(f"case {case}: {problem}" for problem in found)
    return problems


def session_parity(session: Path | None = None, *, contract: Contract = CONTRACT) -> int:
    """Holds every twin in a session to parity, and prints how many twins it compared.

    Twins are two folders under one `<notebook>/<Test_vehicle>/` whose `flight.json` agree on
    `scenario` and `fsw.gnc`, one with `fsw.build` `"python"` and one `"fprime"`. A folder the
    judge skips (`harness.judging.skipped_folders`), or with no twin, is compared to nothing.

    Args:
        session: the session's directory; by default the active one, `current_session()`.
        contract: the contract holding the flights' configurations, the repository's by default.

    Returns:
        The number of twins compared.

    Raises:
        AssertionError: listing every problem `parity` finds, each naming its twin's folders.
    """
    session = current_session() if session is None else session
    skipped = skipped_folders(session, requirements_tree.ROOT)
    flights: dict[tuple[Path, str, str], dict[str, Path]] = {}
    for recorded in recorded_tests(session):
        if recorded.directory.relative_to(session).as_posix() in skipped:
            continue
        flight = json.loads((recorded.directory / "flight.json").read_text())
        key = (recorded.directory.parent, flight["scenario"], flight["fsw"]["gnc"])
        flights.setdefault(key, {})[flight["fsw"]["build"]] = recorded.directory
    twins = [
        (gnc, builds["python"], builds["fprime"])
        for (_, _, gnc), builds in flights.items()
        if {"python", "fprime"} <= builds.keys()
    ]
    problems = [
        f"{python.relative_to(session).as_posix()} against {fprime.name}: {problem}"
        for gnc, python, fprime in twins
        for problem in parity(gnc, python, fprime, contract=contract)
    ]
    print(f"{session}: compared {len(twins)} twin flights")
    if problems:
        raise AssertionError("\n".join(problems))
    return len(twins)
