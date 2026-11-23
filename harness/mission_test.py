"""Missions: what a flight judges, what a mission refuses, and the record a flight leaves.

A test that takes the `configuration` fixture builds or flies a repository configuration against
the repository's requirements tree. Every other test reads a tree it writes in `tmp_path`, by
pointing the tree root at it, so none depends on the repository's own tree. That tree holds two
capabilities, four rungs and two scenarios:

    SYS901 <- SRS901, SRS902, SRS904      SYS902 <- SRS903
    TST901 links SRS901, SRS902, SRS903   TST902 links SRS902

Those tests' flights fly `MockFlight` of `fsw.mock.MOCK`, the test mock `HarnessMock.Mock`,
which claims SYS901, and `MockActuation`, the test mock `MockGnc.Actuator` on the wheel role, which
claims SYS901 too and flies on both builds.
The `variants` fixture renders the other configurations a test needs from two templates.
"""

import importlib
import json
import os
import shutil
import sys
import tomllib
from collections.abc import Callable, Iterator, Sequence
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

import h5py
import numpy as np
import pytest
from wise_dynamics.basilisk.vehicles import VEHICLES
from wise_dynamics.basilisk.vehicles.imu_wheel_spacecraft import ImuWheelSpacecraft

from fsw.codegen import fpp_types
from fsw.codegen.deployment import (
    REPOSITORY,
    Contract,
    configuration_model,
    framework_files,
)
from fsw.codegen.fpp_model import read
from fsw.codegen.members import members
from fsw.codegen.roles import taken
from fsw.mock import MOCK, sub_topology
from harness import requirements_tree
from harness.conftest import write_item
from harness.mission import BUILDS, Mission, _claims, _record_flight, mission_tests
from lab import built

VEHICLE = "imu_spacecraft"
ALPHA = """\
import pytest


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s({duration})
@pytest.mark.sim_runs(1)
async def alpha(ground) -> None:
    {body}
"""

COMPONENT = """module HarnessVariant {{
  @ provides nothing by this line, which is prose: a rendered test mock
{provides}
  passive component {name} {{
    sync input port schedIn: Svc.Sched
{parameter}  }}
}}
"""
"""A test mock component: its name, its `@ provides` lines and, optionally, `PARAMETER`."""

PARAMETER = """    command reg port cmdRegOut
    command recv port cmdIn
    command resp port cmdResponseOut
    param get port prmGetOut
    param set port prmSetOut
    param gain: F64
"""
"""A test mock component's one parameter, with the ports a parameter needs."""

SECOND = """from fsw.codegen.fpp_types import named


class Second:
    def __init__(self, parameters):
        pass

    def step(self, t):
        return named("HarnessVariant.SecondOutputs")(), None
"""
"""The notebook of the variants' `Second`, which claims SYS902 and has no parameter."""

VARIANTS = {
    "SecondOnly": [("second", "HarnessVariant.Second")],
    "Both": [("nav", "HarnessMock.Mock"), ("second", "HarnessVariant.Second")],
    "SecondTwice": [("second", "HarnessVariant.Second"), ("other", "HarnessVariant.Second")],
    "Unclaimed": [("x", "HarnessVariant.Unclaimed")],
    "Classless": [("x", "HarnessVariant.Classless")],
    "Parameterless": [("x", "HarnessVariant.Parameterless")],
}
"""Each rendered configuration's members, `(instance, component)` in the order they run."""


def _component(
    root: Path,
    name: str,
    provides: Sequence[str] = (),
    parameter: bool = False,
    notebook: str | None = None,
) -> Path:
    """Renders a test mock component in a package of its own, with its notebook if it has one.

    Args:
        root: where its folder goes.
        name: the component's name in `HarnessVariant`.
        provides: its claiming annotation lines' text, after the `@ `.
        parameter: whether it has `PARAMETER`.
        notebook: its notebook's source, written as `<folder>/<folder>.py`; None for no notebook.

    Returns:
        Its `.fpp`.
    """
    folder = root / name.lower()
    folder.mkdir()
    fpp = folder / f"{name}.fpp"
    fpp.write_text(
        COMPONENT.format(
            name=name,
            provides="\n".join(f"  @ {line}" for line in provides),
            parameter=PARAMETER if parameter else "",
        )
    )
    (folder / "__init__.py").touch()
    if notebook is not None:
        (folder / f"{folder.name}.py").write_text(notebook)
    return fpp


@pytest.fixture(scope="session")
def variants(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Contract]:
    """The test mock's contract, with the configurations `VARIANTS` names rendered beside its own.

    Rendered once per session, since `fsw.codegen.fpp_types.load` holds each name to one
    definition. The `HarnessVariant` components are `Second` (SYS902, with its notebook),
    `Unclaimed` (no claim, no notebook), `Classless` (a notebook without its class) and
    `Parameterless` (a parameter, and a notebook with its class and no `parameters`). Each is in
    the package `<root>/harness_variants/<folder>/`, and `<root>` is on `sys.path` for the session,
    so each notebook imports as `harness_variants.<folder>.<folder>`.

    Args:
        tmp_path_factory: where the contract is rendered.

    Yields:
        Contract: the contract, `MockFlight` and every variant among its configurations.
    """
    root = tmp_path_factory.mktemp("variants")
    package = root / "harness_variants"
    package.mkdir()
    (package / "__init__.py").touch()
    components = (
        _component(package, "Second", ["provides: SYS902"], notebook=SECOND),
        _component(package, "Unclaimed"),
        _component(package, "Classless", ["provides: SYS901"], notebook=""),
        _component(package, "Parameterless", ["provides: SYS901"], True, "class Parameterless:\n    pass\n"),
    )
    gnc = root / "gnc"
    gnc.mkdir()
    shutil.copy(MOCK.gnc / "MockFlight.fpp", gnc)
    for name, flown in VARIANTS.items():
        (gnc / f"{name}.fpp").write_text(sub_topology(name, flown))
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.syspath_prepend(str(root))
        yield Contract((*MOCK.algorithms, *components), gnc)


def flying(*missions: str, check: str = "", vehicle: str = VEHICLE) -> str:
    """A notebook flying missions, each `Mission` given as its fields after `vehicle`.

    Args:
        *missions: each mission's fields, such as `gnc="MockFlight", ...`, with `contract`.
        check: source defining `check`, placed before the missions.
        vehicle: the vehicle every mission flies.

    Returns:
        The notebook's source, with `MOCK`, `Contract` and `Path` in its namespace.
    """
    calls = ",\n".join(f'    Mission(vehicle="{vehicle}", {m})' for m in missions)
    return f"""
from pathlib import Path

from fsw.codegen.deployment import Contract
from fsw.mock import MOCK
from harness.mission import Mission, mission_tests

{check}

globals().update(mission_tests(
{calls},
))
"""


FLIGHT = flying('gnc="MockFlight", build="python", scenarios=("TST901",), contract=MOCK')
"""A notebook flying `MockFlight` on the Python build through TST901."""


def in_notebook(contract: Contract) -> str:
    """A contract as a notebook's source spells it.

    Args:
        contract: the contract.

    Returns:
        The `Contract(...)` expression.
    """
    algorithms = [str(path) for path in contract.algorithms]
    return f"Contract(tuple(map(Path, {algorithms!r})), Path({str(contract.gnc)!r}))"


@pytest.fixture
def failing_dispersion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes the leo500 scenario fail to disperse, in this process.

    Args:
        monkeypatch: the monkeypatch fixture.
    """
    from wise_dynamics.basilisk.scenarios import SCENARIOS

    def boom(self: object, *args: object, **kwargs: object) -> None:
        """Fail as a dispersion that cannot be drawn.

        Args:
            self: the scenario.
            *args: unused.
            **kwargs: unused.

        Raises:
            RuntimeError: always.
        """
        raise RuntimeError("dispersion failed")

    monkeypatch.setattr(SCENARIOS["leo500"], "disperse", boom)


def write_tree(root: Path, alpha_path: str = "scenarios/alpha.py") -> None:
    """Write the tree the module docstring draws.

    Args:
        root: the project root.
        alpha_path: the file TST901 references for its definition `alpha`.
    """
    for uid in ("SYS901", "SYS902"):
        write_item(root, "sys", uid, links=[])
    for uid, parent in (
        ("SRS901", "SYS901"),
        ("SRS902", "SYS901"),
        ("SRS903", "SYS902"),
        ("SRS904", "SYS901"),
    ):
        write_item(root, "srs", uid, links=[{parent: "stamp"}])
    write_item(
        root,
        "tst",
        "TST901",
        links=[{uid: "stamp"} for uid in ("SRS901", "SRS902", "SRS903")],
        references=[{"path": alpha_path, "keyword": "def alpha(", "type": "file"}],
    )
    write_item(
        root,
        "tst",
        "TST902",
        links=[{"SRS902": "stamp"}],
        references=[{"path": "scenarios/beta.py", "keyword": "def beta(", "type": "file"}],
    )


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tree in `tmp_path`, which the requirements tree functions read by default.

    Args:
        tmp_path: the test's directory.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The project root holding it.
    """
    write_tree(tmp_path)
    monkeypatch.setattr(requirements_tree, "ROOT", tmp_path)
    return tmp_path


def mission(gnc: str = "MockFlight", scenarios: tuple[str, ...] = ("TST901",), **fields: Any) -> Mission:
    """A mission flying a test mock configuration on the Python build.

    Args:
        gnc: the test mock's configuration.
        scenarios: the TST IDs.
        **fields: the mission's other fields; `contract` defaults to `MOCK`.

    Returns:
        The mission.
    """
    fields.setdefault("contract", MOCK)
    return Mission(VEHICLE, gnc, "python", scenarios, **fields)


@pytest.mark.parametrize(
    ("gnc", "scenarios", "rungs", "refused"),
    [
        ("MockFlight", ("TST901",), None, None),
        ("MockFlight", ("TST901",), ("SRS904",), "SRS904"),
        ("SecondOnly", ("TST902",), None, "TST902"),
        ("MockFlight", ("TST901", "TST902"), ("SRS901",), "TST902"),
        ("MockFlight", ("TST901", "TST902"), ("SRS902",), None),
        ("Both", ("TST901",), ("SRS901", "SRS903"), None),
        ("MockFlight", ("TST901",), ("SRS901", "SRS903"), "SRS903"),
    ],
)
def test_a_mission_judges_the_rungs_its_scenarios_reach_under_its_claims(
    tree: Path,
    variants: Contract,
    gnc: str,
    scenarios: tuple[str, ...],
    rungs: tuple[str, ...] | None,
    refused: str | None,
) -> None:
    """A mission keeps its filter, None by default, only when every rung and scenario is judged.

    `MockFlight` claims SYS901, `SecondOnly` SYS902 and `Both` their union. Refused, naming it:
    a filter rung no scenario links (SRS904); a scenario with no rung under the claims (TST902 under
    SYS902 alone); a filter that empties one scenario's flight (SRS901 leaves TST902 nothing); and
    a rung only a claim the configuration lacks owns (SRS903 without SYS902).

    Args:
        tree: the tree.
        variants: the rendered configurations.
        gnc: the configuration.
        scenarios: the TST IDs.
        rungs: the filter.
        refused: what the refusal names, or None when the mission is built.
    """
    if refused:
        with pytest.raises(ValueError, match=refused):
            mission(gnc, scenarios, rungs=rungs, contract=variants)
    else:
        assert mission(gnc, scenarios, rungs=rungs, contract=variants).rungs == rungs


@pytest.mark.parametrize(
    ("changes", "unknown"),
    [
        ({"scenarios": ("TST999",)}, "TST999"),
        ({"rungs": ("SRS999",)}, "SRS999"),
        ({"vehicle": "no_such_vehicle"}, "no_such_vehicle"),
    ],
)
def test_unknown_names_are_refused(tree: Path, changes: dict, unknown: str) -> None:
    """A scenario, rung or vehicle that does not exist is a ValueError naming it.

    Args:
        tree: the tree.
        changes: the field replaced.
        unknown: the name it holds.
    """
    with pytest.raises(ValueError, match=unknown):
        mission().but(**changes)


@pytest.mark.parametrize(
    ("gnc", "build", "dropped", "named"),
    [
        ("NoSuchConfiguration", "python", None, r"NoSuchConfiguration.*'Both'.*'MockFlight'"),
        ("MockFlight", "simulink", None, r"simulink.*'fprime'.*'python'"),
        ("MockFlight", "fprime", None, r"fprime build does not build 'MockFlight'"),
        ("SecondTwice", "python", None, r"Second.*'SecondTwice\.second', 'SecondTwice\.other'"),
        ("Unclaimed", "python", None, r"HarnessVariant\.Unclaimed.*unclaimed/Unclaimed\.fpp"),
        ("MockFlight", "python", "SYS901", r"SYS901.*HarnessMock\.Mock"),
        ("Classless", "python", None, r"classless/classless\.py has no class Classless"),
        ("Parameterless", "python", None, r"parameterless/parameterless\.py.*parameters"),
    ],
)
def test_each_lookup_that_fails_is_refused_naming_what_it_looked_for(
    tree: Path, variants: Contract, gnc: str, build: str, dropped: str | None, named: str
) -> None:
    """A configuration, build, claim, class or `parameters` not found is a ValueError naming it.

    An unknown configuration names the contract's; an unknown build names both builds; the F´ build
    of a configuration it does not build, one whose member has no F´ component, names the
    configuration; a component instanced more than
    once names it and its instances, since `parameters(scenario, vehicle)` gives one tuple per component; a
    component with no `@ provides` names it and its file; a claim the tree lacks names the claim and
    the component; a class missing from its notebook names the notebook and the class; and a
    component with parameters and no `parameters` names the notebook. A vehicle missing a role the
    configuration takes is refused by each build's tick, naming the role, as
    `fsw/python/platform/frame_runner_test.py` and `lab/adapter_test.py` show.

    Args:
        tree: the tree.
        variants: the rendered configurations.
        gnc: the configuration.
        build: the build.
        dropped: a SYS ID taken out of the tree, if any.
        named: what the refusal names, as a pattern.
    """
    if dropped:
        (tree / "docs" / "requirements" / "sys" / f"{dropped}.yml").unlink()

    with pytest.raises(ValueError, match=named):
        Mission(VEHICLE, gnc, build, ("TST901",), contract=variants)


def _vehicle_for(configuration: str) -> str:
    """The first vehicle, by name, that reads each sensor role and writes each actuator role taken.

    Args:
        configuration: a repository configuration.

    Returns:
        The vehicle's name in `VEHICLES`.

    Raises:
        AssertionError: no vehicle carries the configuration's roles, naming them.
    """
    found = taken(configuration_model(configuration), configuration)
    sensors = {role.role for role in found if role.sensor}
    actuators = {role.role for role in found if not role.sensor}
    for name in sorted(VEHICLES):
        vehicle = VEHICLES[name]()
        if sensors <= set(vehicle.readers()) and actuators <= set(vehicle.writers()):
            return name
    raise AssertionError(f"no vehicle reads {sorted(sensors)} and writes {sorted(actuators)} for {configuration}")


def _claimed(configuration: str) -> tuple[list[str], str]:
    """A repository configuration's sorted claims, and the first scenario judging a rung under them.

    Args:
        configuration: the configuration.

    Returns:
        The SYS IDs, the union of its members' components' claims, and the TST ID.
    """
    model = configuration_model(configuration)
    claims = sorted(
        {
            uid
            for group in members(model, configuration).values()
            for instance in group
            for uid in _claims(model, model.components[instance.component])
        }
    )
    tst = requirements_tree.items("TST")
    return claims, next(uid for uid in tst if requirements_tree.flight_rungs(uid, claims))


@pytest.mark.parametrize("build", BUILDS)
def test_each_configuration_s_mission_is_built_on_each_build_without_the_f_prime_extension(
    configuration: str, build: str, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Every lookup succeeds on the repository's contract, and none reaches the F´ extension.

    Each configuration flies the repository's tree through the first scenario that judges a rung
    under its claims, with its extension made absent; only a case's `lab.Adapter` needs it. The
    mission claims the union of its members' claims.

    Args:
        configuration: the configuration.
        build: the build.
        monkeypatch: makes the configuration's extension absent.
        request: gives the F´ build's mission `fprime_configuration`, which skips a configuration
            the F´ build does not build.
    """
    if build == "fprime":
        request.getfixturevalue("fprime_configuration")
    monkeypatch.setitem(sys.modules, f"lab._wise_fsw_{configuration}", None)
    claims, scenario = _claimed(configuration)

    flown = Mission(sorted(VEHICLES)[0], configuration, build, (scenario,))

    assert list(flown._found.capabilities) == claims


@pytest.mark.parametrize("built", [False, True], ids=["extension-absent", "extension-present"])
def test_one_configuration_flown_on_both_builds_is_two_flights(
    fprime_configuration: str, built: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The flight's key holds the build, so the two builds of one scenario are two tests.

    Recording a flight skips the F´ test when the configuration's extension is absent, and removes
    the `flight.json` an earlier flight of it left, so nothing judges or compares the folder; the
    Python test is never skipped.

    Args:
        fprime_configuration: the configuration, one the F´ build builds.
        built: whether the configuration's extension is present.
        monkeypatch: makes the extension absent, or present as a module with a spec.
        tmp_path: holds each test's folder, with a `flight.json` an earlier flight left.
    """
    extension = f"lab._wise_fsw_{fprime_configuration}"
    module = None
    if built:
        module = ModuleType(extension)
        module.__spec__ = ModuleSpec(extension, None)
    monkeypatch.setitem(sys.modules, extension, module)
    _, scenario = _claimed(fprime_configuration)
    python = Mission(sorted(VEHICLES)[0], fprime_configuration, "python", (scenario,))
    missions = {"fprime": python.but(build="fprime"), "python": python}

    [vehicle_class] = mission_tests(*missions.values()).values()

    names = sorted(name for name in vars(vehicle_class) if name.startswith("test_"))
    prefix = f"test_{fprime_configuration}_"
    assert [name.removeprefix(prefix).split("_", 1)[0] for name in names] == ["fprime", "python"]
    assert len({name.removeprefix(prefix).split("_", 1)[1] for name in names}) == 1
    for build, mission in missions.items():
        folder = tmp_path / build
        folder.mkdir()
        (folder / "flight.json").write_text(json.dumps({"fsw": {"build": "stale"}}))
        if build == "fprime" and not built:
            with pytest.raises(pytest.skip.Exception, match="run `just fsw`"):
                _record_flight(mission, scenario, folder)
            assert not (folder / "flight.json").exists()
        else:
            _record_flight(mission, scenario, folder)
            assert json.loads((folder / "flight.json").read_text())["fsw"]["build"] == build


FPRIME_FLIGHT = """
from harness.mission import Mission, mission_tests

globals().update(
    mission_tests(
        Mission(vehicle="{vehicle}", gnc="{gnc}", build="fprime", scenarios=("{scenario}",))
    )
)
"""
"""A notebook flying a repository configuration's F´ build through one scenario."""


def _contents(path: Path) -> dict[str, Any]:
    """Every dataset of a run file, and every root attribute but its creation time.

    Args:
        path: the run file.

    Returns:
        Each dataset's values and attributes by its path, and each root attribute by `@<name>`.
    """
    contents: dict[str, object] = {}

    def visit(name: str, node: object) -> None:
        """Keep a dataset's values and attributes.

        Args:
            name: the node's path in the file.
            node: the group or dataset.
        """
        if isinstance(node, h5py.Dataset):
            contents[name] = (node[()], dict(node.attrs))

    with h5py.File(path, "r") as f:
        f.visititems(visit)
        contents |= {f"@{k}": v for k, v in f.attrs.items() if k != "created_utc"}
    return contents


def test_a_case_flown_after_another_writes_the_run_file_it_writes_alone(
    fprime_configuration: str, rate_groups: list[str], pytester: pytest.Pytester
):
    """Case 1 flown alone and after case 0 in one process gives the same run file, every row.

    Each configuration's F´ build flies the first scenario that judges a rung under its claims.
    The rate groups' health datasets are compared with the GNC members': their `CycleCount` and the
    channels they write only on change are what a deployment kept across cases would carry over.
    It also holds the rate groups' health to F´'s stub clock, under the members' real load: their
    cycle times read 0, where a wall clock would make them differ between the two runs. Case 0's
    run file differs from case 1's, so a comparison that cannot tell cases apart would show.

    Args:
        fprime_configuration: the configuration, one the F´ build builds.
        rate_groups: the configuration's rate groups.
        pytester: the project the flights run in, each run in one process of its own, xdist off.
    """
    if not built(fprime_configuration):
        pytest.skip(f"the F´ build of {fprime_configuration} is absent; run `just fsw`")
    _, scenario = _claimed(fprime_configuration)
    flight = Mission(_vehicle_for(fprime_configuration), fprime_configuration, "fprime", (scenario,))
    [(cls, vehicle_class)] = mission_tests(flight).items()
    [name] = [name for name in vars(vehicle_class) if name.startswith("test_")]
    test = f"test_flights.py::{cls}::{name}"
    pytester.makepyfile(
        test_flights=FPRIME_FLIGHT.format(vehicle=flight.vehicle, gnc=fprime_configuration, scenario=scenario)
    )
    options = ("-p", "no:cacheprovider", "-p", "no:xdist")

    pytester.runpytest_subprocess(*options, f"{test}[1]").assert_outcomes(passed=1)
    [alone] = pytester.path.rglob("run_0001.h5")
    alone = Path(shutil.move(alone, pytester.path / "alone.h5"))
    pytester.runpytest_subprocess(*options, f"{test}[0]", f"{test}[1]").assert_outcomes(passed=2)
    [first] = pytester.path.rglob("run_0000.h5")
    [after] = pytester.path.rglob("run_0001.h5")

    alone, after, first = _contents(alone), _contents(after), _contents(first)
    flown = members(configuration_model(fprime_configuration), fprime_configuration).values()
    gnc = {member.name.rsplit(".", 1)[-1] for group in flown for member in group}
    assert any(name.startswith(tuple(f"tlm/{m}." for m in gnc)) for name in alone)
    for group in rate_groups:
        assert not alone[f"tlm/{group}.CycleTime"][0].any(), group
    assert sorted(alone) == sorted(after)
    for name, value in alone.items():
        np.testing.assert_equal(after[name], value, err_msg=name)
    with pytest.raises(AssertionError):
        np.testing.assert_equal(first, alone)


def test_the_class_a_mission_flies_is_its_notebook_module_s_own(tree: Path) -> None:
    """The class is the one importing the notebook by its dotted name gives, from that module.

    Args:
        tree: the tree.
    """
    [cls] = mission()._found.classes

    notebook = importlib.import_module("fsw.mock.mock")
    assert cls is notebook.Mock
    assert sys.modules[cls.__module__] is notebook


@pytest.mark.parametrize(
    ("lines", "claimed"),
    [
        (["provides: SYS901"], ["SYS901"]),
        (["provides: SYS901", "provides: SYS902"], ["SYS901", "SYS902"]),
        (["provides: SYS901, SYS902"], r"\['SYS901, SYS902'\].*HarnessVariant\.Claims"),
    ],
)
def test_a_component_claims_one_id_per_provides_line(
    tree: Path, tmp_path: Path, lines: list[str], claimed: list[str] | str
) -> None:
    """Each `@ provides:` line is one claim; prose that starts with "provides" is none.

    Two IDs on one line are refused as one ID the tree does not hold.

    Args:
        tree: the tree, which holds SYS901 and SYS902.
        tmp_path: where the test mock's FPP is written.
        lines: its claiming annotation lines.
        claimed: the IDs it claims, or what the refusal names, as a pattern.
    """
    model = read((*framework_files(), _component(tmp_path, "Claims", lines)))
    component = model.components["HarnessVariant.Claims"]

    if isinstance(claimed, str):
        with pytest.raises(ValueError, match=claimed):
            _claims(model, component)
    else:
        assert _claims(model, component) == claimed


@pytest.mark.parametrize(
    ("missions", "match"),
    [
        ([{"rungs": ("SRS901",)}, {"rungs": ("SRS902",)}], "two missions fly"),
        ([{"scenarios": ("TST901", "TST903")}], "the test name"),
    ],
    ids=["same-flight-twice", "same-definition-twice"],
)
def test_two_flights_that_would_share_a_test_are_refused(tree: Path, missions: list[dict], match: str) -> None:
    """A flight cannot be flown twice, whatever each mission judges, nor give two scenarios a name.

    A vehicle, configuration, build and scenario cannot be flown twice. Two TST items that
    reference one scenario definition give one flight's test the same name, which is refused.

    Args:
        tree: the tree.
        missions: the fields of each mission given to `mission_tests`.
        match: what the refusal names.
    """
    (tree / "scenarios").mkdir(exist_ok=True)
    (tree / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=1.0, body="pass"))
    write_item(
        tree,
        "tst",
        "TST903",
        links=[{"SRS901": "stamp"}],
        references=[{"path": "scenarios/alpha.py", "keyword": "def alpha(", "type": "file"}],
    )

    with pytest.raises(ValueError, match=match):
        mission_tests(*(mission(**fields) for fields in missions))


@pytest.fixture
def project(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A pytester project whose root holds the tree.

    Args:
        pytester: the pytester fixture.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The pytester.
    """
    write_tree(pytester.path)
    monkeypatch.setattr(requirements_tree, "ROOT", pytester.path)
    pytester.mkdir("scenarios")
    (pytester.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=1.0, body="pass"))
    return pytester


def test_flight_json_survives_a_case_that_crashes_before_it_flies(
    project: pytest.Pytester, variants: Contract, failing_dispersion: None
) -> None:
    """A case that crashes setting up `sim_scenario` still leaves its flight's facts.

    Two missions fly one vehicle: one judges every rung, one a filter. Each flight's folder holds
    `flight.json` with the scenario, the configuration and build flown, the sorted capabilities and
    the filter or null, and no `build`, since no host was built.

    Args:
        project: the project.
        variants: the rendered configurations, `Both` among them.
        failing_dispersion: makes the scenario fail to disperse.
    """
    project.makepyfile(
        test_flights=flying(
            f'gnc="Both", build="python", scenarios=("TST901",), contract={in_notebook(variants)}',
            'gnc="MockFlight", build="python", scenarios=("TST901",), rungs=("SRS902",), contract=MOCK',
        )
    )

    result = project.runpytest_inprocess("-p", "no:cacheprovider")

    result.assert_outcomes(errors=2)
    result.stdout.fnmatch_lines(["*dispersion failed*"])

    found = {path.parent.name: path for path in project.path.rglob("flight.json")}
    both, flight = "test_Both_python_alpha", "test_MockFlight_python_alpha"
    assert sorted(found) == [both, flight]
    assert found[both].parts[-5:-1] == ("scratch", "test_flights", "Test_imu_spacecraft", both)
    assert json.loads(found[both].read_text()) == {
        "scenario": "TST901",
        "fsw": {"gnc": "Both", "build": "python"},
        "capabilities": ["SYS901", "SYS902"],
        "rungs": None,
    }
    assert json.loads(found[flight].read_text()) == {
        "scenario": "TST901",
        "fsw": {"gnc": "MockFlight", "build": "python"},
        "capabilities": ["SYS901"],
        "rungs": ["SRS902"],
    }


CHECKS = {
    "failing": 'def check(path):\n    return ["the first problem", "the second problem"]',
    "passing": """import h5py


def check(path):
    with h5py.File(path, "r") as f:
        if "commands" not in f.attrs or "truth" not in f:
            return ["not the case's run file"]
    return []
""",
}
"""A check that always fails with two messages, and one passing only the case's run file."""


@pytest.mark.parametrize("check", CHECKS)
def test_a_check_is_given_the_case_s_run_file_and_its_messages_fail_the_case(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult], check: str
) -> None:
    """A check's messages are in the failure, no message passes; the run file is plain.

    The passing check passes only on the finished case's run file, so it was given that file. The
    run file carries no GNC attribute.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
        check: which of `CHECKS`.
    """
    project.makepyfile(
        test_flights=flying(
            'gnc="MockFlight", build="python", scenarios=("TST901",), check=check, contract=MOCK',
            check=CHECKS[check],
        )
    )

    result = fly_in_a_subprocess(project)

    if check == "failing":
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*the first problem*", "*the second problem*"])
    else:
        result.assert_outcomes(passed=1)
    [path] = project.path.rglob("run_0000.h5")
    with h5py.File(path, "r") as f:
        assert not [name for name in f.attrs if "gnc" in name.lower()]
        assert not {"vehicle", "scenario_item", "capabilities"} & set(f.attrs)


SELF = """
import pytest

from fsw.mock import MOCK
from harness.mission import Mission, mission_tests
{before}
globals().update(mission_tests(Mission(
    vehicle="imu_spacecraft", gnc="MockFlight", build="python", scenarios=("TST901",), contract=MOCK
)))
{after}
"""
"""A notebook flying a scenario it defines itself, `alpha`, defined before or after its mission."""

ALPHA_HERE = """

@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s(1.0)
@pytest.mark.sim_runs(1)
def alpha():
    pass
"""
"""The scenario definition `SELF` places."""


@pytest.mark.parametrize("defined_first", [True, False], ids=["defined-first", "flown-first"])
def test_a_notebook_flies_a_scenario_it_defines_only_once_it_has_defined_it(
    project: pytest.Pytester, defined_first: bool
) -> None:
    """A file whose TST item references itself finds its own definition while it loads.

    A file whose missions come before the definition they reference fails, naming it.

    Args:
        project: the project.
        defined_first: whether the definition comes before the missions.
    """
    write_tree(project.path, alpha_path="test_self.py")
    before, after = (ALPHA_HERE, "") if defined_first else ("", ALPHA_HERE)
    project.makepyfile(test_self=SELF.format(before=before, after=after))

    result = project.runpytest_inprocess("--collect-only", "-q", "-p", "no:cacheprovider")

    if defined_first:
        result.stdout.fnmatch_lines(["*Test_imu_spacecraft::test_MockFlight_python_alpha*"])
    else:
        result.assert_outcomes(errors=1)
        result.stdout.fnmatch_lines(["*ValueError*alpha*"])


def test_a_scenario_file_that_raised_on_import_is_imported_afresh_once_fixed(
    tree: Path,
) -> None:
    """A failed import leaves nothing registered, so the lookup after the fix succeeds.

    Args:
        tree: the tree.
    """
    scenarios = tree / "scenarios"
    scenarios.mkdir()
    (scenarios / "alpha.py").write_text('raise RuntimeError("alpha is broken")\n')
    flown = mission()

    with pytest.raises(RuntimeError, match="alpha is broken"):
        mission_tests(flown)

    (scenarios / "alpha.py").write_text(ALPHA.format(duration=1.0, body="pass"))
    [vehicle_class] = mission_tests(flown).values()
    assert [name for name in vars(vehicle_class) if name.startswith("test_")] == ["test_MockFlight_python_alpha"]


def test_a_flight_runs_the_procedure_on_the_build_s_radio_edge_for_the_scenario_s_duration(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """The configuration's build, hosted by `FswHost`, flies through the ground on its radio edge.

    The run file holds the truth, an empty command log and the test mock's nav channels, and ends
    at the TST definition's `sim_duration_s`, so the harness bound the stopping rule. `flight.json`
    names the configuration and build flown, and the build's identity.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    (project.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=20.0, body="pass"))
    project.makepyfile(test_flights=FLIGHT)

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=1)
    [path] = project.path.rglob("run_0000.h5")
    with h5py.File(path, "r") as f:
        assert sorted(f["tlm"]) == ["nav.bodyEciAttitude", "nav.bodyEciPos", "nav.bodyEciVel"]
        assert json.loads(f.attrs["commands"]) == []
        assert "r_N" in f["truth"]
        assert f["t_s"][-1] == 20.0
    [flight] = project.path.rglob("flight.json")
    assert json.loads(flight.read_text()) == {
        "scenario": "TST901",
        "capabilities": ["SYS901"],
        "rungs": None,
        "fsw": {"gnc": "MockFlight", "build": "python"},
        "build": {"host": "fsw.python.FrameRunner"},
    }


def test_a_case_s_parameter_record_is_written_beside_its_run_file_from_each_member(
    project: pytest.Pytester,
    variants: Contract,
    fly_in_a_subprocess: Callable[..., pytest.RunResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each member's tuple, from its notebook's `parameters`, under its qualified instance.

    `Mock`'s gain is the case's scenario's Earth `mu`; `Second` has no parameter and no
    `parameters`, so its entry is empty.

    Args:
        project: the project.
        variants: the rendered configurations, `Both` among them.
        fly_in_a_subprocess: runs the project in a subprocess.
        monkeypatch: puts the variants' root on the subprocess's path.
    """
    path = [str(variants.gnc.parent), *filter(None, [os.environ.get("PYTHONPATH")])]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(path))
    project.makepyfile(
        test_flights=flying(f'gnc="Both", build="python", scenarios=("TST901",), contract={in_notebook(variants)}')
    )

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=1)
    [run] = project.path.rglob("run_0000.h5")
    record = json.loads(run.with_suffix(".prm.json").read_text())
    assert record == {"Both.nav": {"gain": 3.986004360e14}, "Both.second": {}}


def test_the_definition_s_ground_period_mark_sets_the_ground_s_period(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """A definition marked `sim_ground_period_s(10.0)` is flown by a ground with that period.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    definition = ALPHA.format(duration=20.0, body="assert ground.period_s == 10.0")
    (project.path / "scenarios" / "alpha.py").write_text(
        definition.replace(
            "@pytest.mark.sim_runs(1)",
            "@pytest.mark.sim_runs(1)\n@pytest.mark.sim_ground_period_s(10.0)",
        )
    )
    project.makepyfile(test_flights=FLIGHT)

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    ("body", "failure"),
    [
        (
            "await ground.until(lambda: False, timeout_s=3.0)",
            "TimeoutError: timed out at t = 3.0 s waiting until the condition at alpha.py:*",
        ),
        (
            "await ground.sleep(100.0)",
            "TimeoutError: the flight ended at t = 20.0 s * waiting until t = 100.0 s",
        ),
        ('await ground.send("nav.fail")', "ZeroDivisionError: the tick's own bug"),
    ],
    ids=["procedure-raises", "procedure-still-waiting", "flight-software-raises"],
)
def test_a_case_fails_as_the_exception_that_ended_it_and_writes_no_run_file(
    project: pytest.Pytester,
    fly_in_a_subprocess: Callable[..., pytest.RunResult],
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    failure: str,
) -> None:
    """The case fails with the procedure's or the flight software's own exception, not Basilisk's.

    A procedure waiting for what never comes fails with its own `TimeoutError`; one still waiting
    when the 20 s flight ends fails naming its wait; and a bug in an algorithm's step, the test mock
    commanded to fail, fails as itself.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
        monkeypatch: widens the subprocess's summary line to hold the exception.
        body: the procedure's body.
        failure: the exception the case fails with, as a pattern.
    """
    (project.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=20.0, body=body))
    project.makepyfile(test_flights=FLIGHT)
    monkeypatch.setenv("COLUMNS", "200")

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines([f"FAILED * - {failure}"])
    assert list(project.path.rglob("run_0000.h5")) == []


def test_a_procedure_that_forgets_an_await_fails_the_case(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """Under the repository's warning filters, a `ground.sleep` never awaited fails the case.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    pyproject = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())
    filters = pyproject["tool"]["pytest"]["ini_options"]["filterwarnings"]
    project.makeini("[pytest]\nfilterwarnings =\n" + "".join(f"    {f}\n" for f in filters))
    (project.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=3.0, body="ground.sleep(1.0)"))
    project.makepyfile(test_flights=FLIGHT)

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*coroutine 'Ground.sleep' was never awaited*"])


def test_a_later_cases_base_write_keeps_the_build_an_earlier_case_merged(
    project: pytest.Pytester, failing_dispersion: None
) -> None:
    """A case that crashes in setup after its base write leaves the `build` already recorded.

    `flight.json` holds the `build` an earlier case merged. This case's fixture writes the flight's
    base facts, then its scenario fails to disperse, so the base write must merge into the file
    rather than replace it.

    Args:
        project: the project.
        failing_dispersion: makes the scenario fail to disperse.
    """
    flight = project.path.joinpath(
        "monte_carlo",
        "scratch",
        "test_flights",
        "Test_imu_spacecraft",
        "test_MockFlight_python_alpha",
        "flight.json",
    )
    flight.parent.mkdir(parents=True)
    flight.write_text(json.dumps({"build": {"host": "fsw.python.FrameRunner"}}))
    project.makepyfile(test_flights=FLIGHT)

    result = project.runpytest_inprocess("-p", "no:cacheprovider")

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*dispersion failed*"])
    assert json.loads(flight.read_text()) == {
        "scenario": "TST901",
        "capabilities": ["SYS901"],
        "rungs": None,
        "fsw": {"gnc": "MockFlight", "build": "python"},
        "build": {"host": "fsw.python.FrameRunner"},
    }


def test_an_interrupted_flight_json_write_leaves_the_old_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write goes to a temporary file beside the target and lands by `os.replace`.

    A write interrupted where it would land raises, leaves the previous file whole and leaves no
    temporary file behind.

    Args:
        tmp_path: the test's directory.
        monkeypatch: the monkeypatch fixture.
    """
    from harness.mission import _merge_json

    target = tmp_path / "flight.json"
    _merge_json(target, {"scenario": "TST901"})

    def interrupted(source: str | Path, destination: str | Path) -> None:
        """Fail as a write killed at the rename.

        Args:
            source: the temporary file.
            destination: the file it would land as.

        Raises:
            OSError: always.
        """
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", interrupted)

    with pytest.raises(OSError, match="interrupted"):
        _merge_json(target, {"build": {"host": "stub"}})

    assert json.loads(target.read_text()) == {"scenario": "TST901"}
    assert list(tmp_path.iterdir()) == [target]


def test_the_mock_actuator_s_command_spins_the_wheel_through_its_writer_alike_on_both_builds(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """MockActuation's wheel command reaches the wheel vehicle's writer from each build.

    The test mock sends one constant command every other 1 s tick from the first, which the wheel
    keeps between, so the wheel's spin
    momentum, Js (Omega + gsHat . omega_BN_B), gains the command's torque on the wheel times the
    time since then, as Basilisk's balanced-wheel model says, from the vehicle's own wheel. The two
    builds' recorded wheel speeds are bit-identical, so the F´ build's bytes carry the same
    command. The F´ flight is skipped without the F´ build of MockActuation, as every F´ flight is.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    from fsw.mock.actuator.actuator import Actuator

    built_fprime = built("MockActuation")
    (project.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=10.0, body="pass"))
    missions = [f'gnc="MockActuation", build="{build}", scenarios=("TST901",), contract=MOCK' for build in BUILDS]
    project.makepyfile(test_flights=flying(*missions, vehicle="imu_wheel_spacecraft"))

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=2 if built_fprime else 1, skipped=0 if built_fprime else 1)
    vehicle = ImuWheelSpacecraft()
    [wheel] = vehicle.wheel.ReactionWheelData
    fpp_types.load(MOCK)
    [command] = Actuator(None).step(0.0)[0]
    torque = command.motorTorque[0]
    assert 0.0 < torque < wheel.u_max
    speeds = {}
    for build in ("python", "fprime") if built_fprime else ("python",):
        [path] = project.path.rglob(f"test_MockActuation_{build}_*/run_0000.h5")
        with h5py.File(path, "r") as f:
            t_s, speed = f["t_s"][()], f["truth/wheel_speed"][()]
            rate = f["truth/omega_BN_B"][()]
        momentum = wheel.Js * (speed + rate @ np.array(wheel.gsHat_B).flatten())
        assert speed[-1] != 0.0, build
        np.testing.assert_allclose(
            momentum - momentum[0],
            torque * np.clip(t_s - 1.0, 0.0, None),
            rtol=1e-9,
            atol=1e-12,
            err_msg=build,
        )
        speeds[build] = speed
    if built_fprime:
        assert speeds["fprime"].tobytes() == speeds["python"].tobytes()
