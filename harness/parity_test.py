"""Parity: two builds' flights of one configuration, compared on what the contract declares.

Twins fly the harness's test mock, `MockFlight` of `harness.mock.MOCK`, and every name the tests
write or change is read from its model: its member's channels, commands and parameters, and its
rate group's channels as an extra. Each test changes one side of an identical twin.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import h5py
import numpy as np
import pytest
from wise_dynamics.sessions import crash_path, run_path

from fsw.codegen.deployment import configuration_model
from fsw.codegen.fpp_model import Array, Enum
from fsw.codegen.members import members
from harness import requirements_tree
from harness.mock import MOCK
from harness.parity import parity, session_parity

GNC = "MockFlight"
MODEL = configuration_model(GNC, contract=MOCK)
[[GROUP, (MEMBER,)]] = members(MODEL, GNC).items()
INSTANCE = MEMBER.name.split(".", 1)[1]
COMPONENT = MODEL.components[MEMBER.component]
FLOAT = next(c.name for c in COMPONENT.channels if isinstance(MODEL.types.get(c.type), Array))
ENUM = next(c.name for c in COMPONENT.channels if isinstance(MODEL.types.get(c.type), Enum))
ARGUED = next(c for c in COMPONENT.commands if any(a.type == "F64" for a in c.args))
ARGUMENT = next(a.name for a in ARGUED.args if a.type == "F64")
PARAMETER = COMPONENT.parameters[0].name
RATE_GROUP = GROUP.removeprefix(f"{GNC}.")
RATE_GROUP_CHANNEL = MODEL.components[MODEL.instances[GROUP].component].channels[0].name

CASES = 2
"""Cases each flight plans."""

WRITES = 5
"""Writes of each channel in a case."""


def _values(type_ref: str, rows: tuple[int, ...], rng: np.random.Generator) -> np.ndarray:
    """Values of an FPP type as a run file or command log holds them.

    Args:
        type_ref: the type, such as `Gnc.Vector3` or `F64`.
        rows: the leading shape.
        rng: the generator.

    Returns:
        An enum's constants' names, cycled; otherwise float64, an array's size as the last axis.
    """
    definition = MODEL.types.get(type_ref)
    if isinstance(definition, Enum):
        names = list(definition.constants)
        return np.array([names[i % len(names)] for i in range(int(np.prod(rows)))]).reshape(rows)
    size = (definition.size,) if isinstance(definition, Array) else ()
    return rng.uniform(-7e6, 7e6, (*rows, *size))


def _log(rng: np.random.Generator) -> list[dict[str, Any]]:
    """A command log sending each contract command once, each answered `OK` a second later.

    Args:
        rng: the generator.

    Returns:
        The log, as the ground keeps it.
    """
    return [
        {
            "t_s": 10.0 * context,
            "name": f"{INSTANCE}.{command.name}",
            "args": {a.name: _values(a.type, (), rng).tolist() for a in command.args},
            "context": context,
            "response": "OK",
            "response_t_s": 10.0 * context + 1.0,
            "reason": None,
        }
        for context, command in enumerate(COMPONENT.commands, start=1)
    ]


def _put(f: h5py.File, name: str, values: np.ndarray) -> None:
    """Write a dataset, strings as HDF5 strings, as a run file holds an enum channel.

    Args:
        f: the open run file.
        name: the dataset's path.
        values: its values.
    """
    if values.dtype.kind in "UO":
        f.create_dataset(name, data=values.astype(object), dtype=h5py.string_dtype())
    else:
        f[name] = values


def _write_flight(folder: Path, build: str, scenario: str, gnc: str, nodeid: str) -> None:
    """Write one flight of `GNC` as a campaign leaves it, its values the same for every build.

    Args:
        folder: the flight's folder.
        build: `"python"` or `"fprime"`.
        scenario: the TST ID it flew.
        gnc: the configuration its `flight.json` names.
        nodeid: the test's node ID.
    """
    folder.mkdir(parents=True)
    (folder / "planned.json").write_text(json.dumps({"runs": CASES, "nodeid": nodeid}))
    (folder / "flight.json").write_text(
        json.dumps({"scenario": scenario, "fsw": {"gnc": gnc, "build": build}})
    )
    for case in range(CASES):
        rng = np.random.default_rng(case)
        record = {MEMBER.name: {p.name: float(rng.uniform(1.0, 2.0)) for p in COMPONENT.parameters}}
        run = run_path(folder, case)
        run.with_suffix(".prm.json").write_text(json.dumps(record))
        t_s = np.arange(WRITES, dtype=float)
        with h5py.File(run, "w") as f:
            f["t_s"] = t_s
            f.attrs["commands"] = json.dumps(_log(rng))
            for channel in COMPONENT.channels:
                _put(f, f"tlm/{INSTANCE}.{channel.name}", _values(channel.type, (WRITES,), rng))
                f[f"tlm_t/{INSTANCE}.{channel.name}"] = t_s


Flier = Callable[..., Path]


@pytest.fixture
def fly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flier:
    """Writes flights into a session in `tmp_path`, under a tree root whose notebook exists.

    Args:
        tmp_path: holds the root, its notebook `notebook.py`, and the session `session/`.
        monkeypatch: points the requirements tree's root at `tmp_path`.

    Returns:
        A function taking the build, and optionally the scenario, the notebook, the vehicle's
        class and the configuration `flight.json` names, writing that flight and returning its
        folder.
    """
    monkeypatch.setattr(requirements_tree, "ROOT", tmp_path)
    (tmp_path / "notebook.py").touch()

    def flight(
        build: str,
        scenario: str = "TST901",
        notebook: str = "notebook",
        vehicle: str = "Test_vehicle",
        gnc: str = GNC,
    ) -> Path:
        """Write one flight.

        Args:
            build: `"python"` or `"fprime"`.
            scenario: the TST ID it flew.
            notebook: the notebook it was flown from, without `.py`.
            vehicle: its vehicle's test class.
            gnc: the configuration its `flight.json` names.

        Returns:
            Its folder.
        """
        test = f"test_{gnc}_{build}_{scenario}"
        folder = tmp_path / "session" / notebook / vehicle / test
        _write_flight(folder, build, scenario, gnc, f"{notebook}.py::{vehicle}::{test}")
        return folder

    return flight


class Twin(NamedTuple):
    """One flight on each build, identical.

    Attributes:
        python: the Python build's folder.
        fprime: the F´ build's folder.
    """

    python: Path
    fprime: Path


@pytest.fixture
def twin(fly: Flier) -> Twin:
    """One identical flight on each build.

    Args:
        fly: writes a flight.

    Returns:
        The twin.
    """
    return Twin(fly("python"), fly("fprime"))


def _dataset(folder: Path, name: str, change: Callable[[np.ndarray], np.ndarray | None]) -> None:
    """Change one dataset of case 0's run file, or remove it when `change` returns None.

    Args:
        folder: the flight's folder.
        name: the dataset's path.
        change: takes the values and gives the new ones.
    """
    with h5py.File(run_path(folder, 0), "a") as f:
        values = f[name][()] if name in f else None
        new = change(values)
        if name in f:
            del f[name]
        if new is not None:
            _put(f, name, new)


def _commands(folder: Path, change: Callable[[list[dict[str, Any]]], None]) -> None:
    """Change case 0's command log in place.

    Args:
        folder: the flight's folder.
        change: takes the log and changes it.
    """
    with h5py.File(run_path(folder, 0), "a") as f:
        log = json.loads(f.attrs["commands"])
        change(log)
        f.attrs["commands"] = json.dumps(log)


def _entry(log: list[dict[str, Any]]) -> dict[str, Any]:
    """The entry of the command with a float argument.

    Args:
        log: the command log.

    Returns:
        The entry.
    """
    return next(e for e in log if e["name"] == f"{INSTANCE}.{ARGUED.name}")


def _scaled(relative: float) -> Callable[[np.ndarray], np.ndarray]:
    """A change adding `relative` times the values' largest magnitude to their first element.

    Args:
        relative: the change, relative to the largest magnitude.

    Returns:
        The change.
    """

    def change(values: np.ndarray) -> np.ndarray:
        """Add the change.

        Args:
            values: the values.

        Returns:
            The values changed.
        """
        new = values.copy()
        new.flat[0] += relative * np.max(np.abs(values))
        return new

    return change


def _nan(values: np.ndarray) -> np.ndarray:
    """The values with their first element NaN.

    Args:
        values: the values.

    Returns:
        The values changed.
    """
    new = values.copy()
    new.flat[0] = np.nan
    return new


def _argument(relative: float) -> Callable[[list[dict[str, Any]]], None]:
    """A change of the float argument by `relative` times its magnitude.

    Args:
        relative: the change.

    Returns:
        The change of a log.
    """

    def change(log: list[dict[str, Any]]) -> None:
        """Change the argument.

        Args:
            log: the command log.
        """
        args = _entry(log)["args"]
        args[ARGUMENT] *= 1.0 + relative

    return change


def _extras(folder: Path) -> None:
    """Add everything the spec does not compare to one flight's case 0.

    A contract command's free-text reason, the parameter's F´ set command and the dispatcher's
    no-op command among the contract's, which renumbers every context, the rate group's channel,
    and a channel the member does not declare.

    Args:
        folder: the flight's folder.
    """

    def change(log: list[dict[str, Any]]) -> None:
        """Add the commands and the reason.

        Args:
            log: the command log.
        """
        log[0]["reason"] = "free text"
        for name in (f"{INSTANCE}.{PARAMETER.upper()}_PRM_SET", "cmdDisp.CMD_NO_OP"):
            log.insert(1, {**log[0], "name": name, "args": {}})
        for context, entry in enumerate(log, start=1):
            entry["context"] = context

    _commands(folder, change)
    for name in (f"{RATE_GROUP}.{RATE_GROUP_CHANNEL}", f"{INSTANCE}.undeclared"):
        _dataset(folder, f"tlm/{name}", lambda _: np.arange(WRITES, dtype=float))
        _dataset(folder, f"tlm_t/{name}", lambda _: np.arange(WRITES, dtype=float))


def _record(folder: Path, change: Callable[[dict[str, Any]], Any]) -> None:
    """Change the member's parameters in case 0's record in place.

    Args:
        folder: the flight's folder.
        change: takes the member's parameters by name and changes them.
    """
    path = run_path(folder, 0).with_suffix(".prm.json")
    record = json.loads(path.read_text())
    change(record[MEMBER.name])
    path.write_text(json.dumps(record))


def _bump(parameters: dict[str, Any]) -> None:
    """Change the parameter's value.

    Args:
        parameters: the member's parameters by name.
    """
    parameters[PARAMETER] += 1.0


def _response(field: str, value: Any) -> Callable[[list[dict[str, Any]]], None]:
    """A change of one field of the float-argument command's entry.

    Args:
        field: the field.
        value: its new value.

    Returns:
        The change of a log.
    """

    def change(log: list[dict[str, Any]]) -> None:
        """Change the field.

        Args:
            log: the command log.
        """
        _entry(log)[field] = value

    return change


def _crash(folder: Path) -> None:
    """Make case 1 a crash: its crash record in place of its run file.

    Args:
        folder: the flight's folder.
    """
    run_path(folder, 1).unlink()
    crash_path(folder, 1).write_text(json.dumps({"error": "ZeroDivisionError"}))


def _planned(folder: Path) -> None:
    """Make the flight plan one case more than it ran.

    Args:
        folder: the flight's folder.
    """
    (folder / "planned.json").write_text(json.dumps({"runs": CASES + 1, "nodeid": "x"}))


FLOAT_TLM = f"tlm/{INSTANCE}.{FLOAT}"
COMMAND = f"{INSTANCE}.{ARGUED.name}"
OTHER_COMMAND = f"{INSTANCE}.{next(c.name for c in COMPONENT.commands if c != ARGUED)}"

CHANGES = [
    ("identical", lambda t: None, None),
    ("float-within", lambda t: _dataset(t.fprime, FLOAT_TLM, _scaled(1e-13)), None),
    ("float-beyond", lambda t: _dataset(t.fprime, FLOAT_TLM, _scaled(1e-11)), FLOAT_TLM),
    (
        "enum-differs",
        lambda t: _dataset(t.fprime, f"tlm/{INSTANCE}.{ENUM}", lambda v: v[::-1]),
        f"tlm/{INSTANCE}.{ENUM}",
    ),
    (
        "write-time",
        lambda t: _dataset(t.fprime, f"tlm_t/{INSTANCE}.{FLOAT}", lambda v: v + 1e-9),
        f"tlm_t/{INSTANCE}.{FLOAT}",
    ),
    ("channel-python-only", lambda t: _dataset(t.fprime, FLOAT_TLM, lambda v: None), FLOAT_TLM),
    ("channel-fprime-only", lambda t: _dataset(t.python, FLOAT_TLM, lambda v: None), FLOAT_TLM),
    ("nan-one-side", lambda t: _dataset(t.fprime, FLOAT_TLM, _nan), FLOAT_TLM),
    (
        "nan-both-sides",
        lambda t: [_dataset(side, FLOAT_TLM, _nan) for side in t],
        None,
    ),
    (
        "missing-command",
        lambda t: _commands(t.fprime, lambda log: log.remove(_entry(log))),
        "contract commands",
    ),
    ("argument-within", lambda t: _commands(t.fprime, _argument(1e-13)), None),
    ("argument-beyond", lambda t: _commands(t.fprime, _argument(1e-11)), f"argument {ARGUMENT}"),
    (
        "response",
        lambda t: _commands(t.fprime, _response("response", "VALIDATION_ERROR")),
        f"{COMMAND}: response ",
    ),
    (
        "response-time",
        lambda t: _commands(t.fprime, _response("response_t_s", 99.0)),
        f"{COMMAND}: response_t_s ",
    ),
    (
        "command-time",
        lambda t: _commands(t.fprime, _response("t_s", 99.0)),
        f"{COMMAND}: t_s ",
    ),
    (
        "command-name",
        lambda t: _commands(t.fprime, _response("name", OTHER_COMMAND)),
        f"{COMMAND}: name ",
    ),
    (
        "argument-missing",
        lambda t: _commands(t.fprime, lambda log: _entry(log)["args"].pop(ARGUMENT)),
        f"{COMMAND}: arguments ",
    ),
    (
        "shape",
        lambda t: _dataset(t.fprime, FLOAT_TLM, lambda v: v[:, :-1]),
        f"{FLOAT_TLM} is float64",
    ),
    ("parameter", lambda t: _record(t.fprime, _bump), f"differs in ['{MEMBER.name}.{PARAMETER}']"),
    (
        "parameter-one-side",
        lambda t: _record(t.fprime, lambda parameters: parameters.pop(PARAMETER)),
        f"differs in ['{MEMBER.name}.{PARAMETER}']",
    ),
    ("case-one-side", lambda t: run_path(t.fprime, 1).unlink(), "case 1"),
    ("crash-fprime", lambda t: _crash(t.fprime), "case 1: crashed on fprime"),
    ("crash-python", lambda t: _crash(t.python), "case 1: crashed on python"),
    ("crash-both", lambda t: [_crash(side) for side in t], "case 1: crashed on python and fprime"),
    ("planned", lambda t: _planned(t.fprime), "planned"),
    ("extras-fprime", lambda t: _extras(t.fprime), None),
    ("extras-python", lambda t: _extras(t.python), None),
]
"""Each change of an identical twin, with a fragment of the one problem it makes, or None."""

MALFORMED = [
    (
        "write-times-missing",
        lambda t: _dataset(t.fprime, f"tlm_t/{INSTANCE}.{FLOAT}", lambda v: None),
        KeyError,
    ),
    (
        "record-missing",
        lambda t: run_path(t.fprime, 0).with_suffix(".prm.json").unlink(),
        FileNotFoundError,
    ),
]
"""Each change leaving a case's run without a file or dataset the harness always writes with it."""


@pytest.mark.parametrize(
    ("change", "problem"), [c[1:] for c in CHANGES], ids=[c[0] for c in CHANGES]
)
def test_parity_reports_each_compared_difference_once_and_never_an_extra(
    twin: Twin, change: Callable[[Twin], None], problem: str | None
) -> None:
    """A twin agrees until a compared item differs, and then reports that one problem.

    Args:
        twin: an identical twin.
        change: changes it.
        problem: a fragment of the one problem, or None when the twin still agrees.
    """
    change(twin)

    found = parity(GNC, twin.python, twin.fprime, contract=MOCK)

    if problem is None:
        assert found == []
    else:
        assert len(found) == 1, found
        assert problem in found[0]


PYTHON = {"build": "python"}
FPRIME = {"build": "fprime"}


@pytest.mark.parametrize(
    ("change", "error"), [m[1:] for m in MALFORMED], ids=[m[0] for m in MALFORMED]
)
def test_a_case_missing_what_the_harness_writes_with_its_run_raises(
    twin: Twin, change: Callable[[Twin], None], error: type[Exception]
) -> None:
    """A malformed case is not a disagreement: parity raises rather than reporting it.

    Args:
        twin: an identical twin.
        change: removes a channel's write times or the case's parameter record on one side.
        error: the exception reading the missing item raises.
    """
    change(twin)

    with pytest.raises(error):
        parity(GNC, twin.python, twin.fprime, contract=MOCK)


SESSIONS = [
    ("twin", [PYTHON, FPRIME], False, 1, None),
    ("twin-disagrees", [PYTHON, FPRIME], True, 1, FLOAT_TLM),
    ("lone-python", [PYTHON], True, 0, None),
    ("other-scenario", [PYTHON, {**FPRIME, "scenario": "TST902"}], True, 0, None),
    ("other-vehicle", [PYTHON, {**FPRIME, "vehicle": "Test_other"}], True, 0, None),
    ("other-configuration", [PYTHON, {**FPRIME, "gnc": "OtherFlight"}], True, 0, None),
    ("skipped", [{**PYTHON, "notebook": "gone"}, {**FPRIME, "notebook": "gone"}], True, 0, None),
]
"""Each session's flights, whether its F´ flights disagree, the twins compared and the problem."""


@pytest.mark.parametrize(
    ("flights", "disagree", "compared", "problem"),
    [s[1:] for s in SESSIONS],
    ids=[s[0] for s in SESSIONS],
)
def test_session_parity_compares_each_twin_flight_json_pairs(
    fly: Flier,
    capsys: pytest.CaptureFixture[str],
    flights: list[dict[str, str]],
    disagree: bool,
    compared: int,
    problem: str | None,
) -> None:
    """Twins are the flights of one vehicle, scenario and configuration on the two builds.

    A flight with no twin, or in a folder the judge skips, is compared to nothing.

    Args:
        fly: writes a flight.
        capsys: captures the count printed.
        flights: each flight's arguments to `fly`; the notebook `gone` is absent from the root.
        disagree: whether each F´ flight's float channel is changed beyond tolerance.
        compared: the twins compared.
        problem: a fragment of the problem raised, or None when nothing is raised.
    """
    for flight in flights:
        folder = fly(**flight)
        if disagree and flight["build"] == "fprime":
            _dataset(folder, FLOAT_TLM, _scaled(1e-11))
    session = requirements_tree.ROOT / "session"

    if problem is None:
        assert session_parity(session, contract=MOCK) == compared
    else:
        with pytest.raises(AssertionError) as raised:
            session_parity(session, contract=MOCK)
        assert problem in str(raised.value)
        assert "Test_vehicle/test_MockFlight_python_TST901" in str(raised.value)

    assert f"compared {compared} twin" in capsys.readouterr().out
