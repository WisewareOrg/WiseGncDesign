"""Missions: a GNC configuration flown on a build and a vehicle through scenarios, judged on rungs.

A mission lives outside the requirements tree. It names a configuration, a GNC sub-topology of the
contract, and a build, `"python"` or `"fprime"`, which together are its FSW. Each algorithm
component of the configuration claims the capabilities (SYS items) it provides with `@ provides`
lines in its FPP, and the configuration claims their union; the mission picks the rungs (SRS items)
to judge and the scenarios (TST items) to fly. A component's class and `parameters(scenario)` are
found in its algorithm's notebook, `<folder>/<folder>.py` beside its `.fpp`, by the component's
name. `mission_tests` turns missions into Monte Carlo tests for a notebook's globals: a class per
vehicle, holding a test per configuration, build and scenario, so each flight's runs have a folder
of their own.
"""

import functools
import importlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import weakref
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest
from wise_dynamics.basilisk import FswHost
from wise_dynamics.basilisk.vehicles import VEHICLES
from wise_dynamics.sessions import run_path

from fsw.codegen import fpp_types
from fsw.codegen.deployment import (
    CONTRACT,
    Contract,
    configuration_model,
    configurations,
    fprime_configurations,
)
from fsw.codegen.fpp_model import Component, Model
from fsw.codegen.members import members
from fsw.python import FrameRunner
from ground import parameters
from ground.fprime_station import FprimeStation
from ground.procedures import Ground
from harness import requirements_tree
from lab import Adapter, built

BUILDS = ("fprime", "python")
"""The builds a configuration flies on: the F´ build in the lab, and the Python build."""

_PROVIDES = "provides:"
"""What starts a component's annotation line claiming a capability."""


class _Member(NamedTuple):
    """An algorithm member of a configuration, as its flights build it.

    Attributes:
        instance: its instance's qualified name, `<configuration>.<instance>`.
        tuple_type: its component's `<Name>Parameters` tuple.
        parameters: its notebook's `parameters(scenario)`, or None when the tuple has no field.
    """

    instance: str
    tuple_type: type
    parameters: Callable[[Any], Any] | None


class _Configuration(NamedTuple):
    """What a mission's lookups found for its configuration and build.

    Attributes:
        capabilities: the SYS IDs its members' components claim, sorted.
        members: its algorithm members, in the order its rate groups run them.
        classes: each member's component's class, for the Python build; empty for the F´ build.
    """

    capabilities: tuple[str, ...]
    members: tuple[_Member, ...]
    classes: tuple[type, ...]


def _claims(model: Model, component: Component) -> list[str]:
    """The SYS IDs a component claims: one per `@ provides:` line of its FPP.

    Args:
        model: the model holding the component.
        component: the component.

    Returns:
        The IDs.

    Raises:
        ValueError: the component has no `@ provides` line, or claims an ID the requirements tree
            does not hold, naming the component.
    """
    claimed = [
        line.removeprefix(_PROVIDES).strip() for line in model.annotations[component.name] if line.startswith(_PROVIDES)
    ]
    if not claimed:
        raise ValueError(f"{component.name} claims no capability: {component.file} has no `@ provides` line")
    unknown = [uid for uid in claimed if uid not in requirements_tree.items("SYS")]
    if unknown:
        raise ValueError(f"no capability {unknown} in the requirements tree, claimed by {component.name}")
    return claimed


def _notebook(component: Component) -> ModuleType:
    """The notebook of a component's algorithm, `<package>/<package>.py` beside its `.fpp`.

    It is imported by its dotted name from its package root, the folder above the topmost of the
    folders, walking up from the notebook's, that hold an `__init__.py`, as pytest names a test
    module. The name is the same in a kernel, a worker and the suite, and a module already
    imported under it is the notebook. A notebook missing, a root not on `sys.path`, or a notebook
    raising while it imports, raises as Python's import does.

    Args:
        component: the component.

    Returns:
        The notebook's module.
    """
    path = (component.file.parent / f"{component.file.parent.name}.py").resolve()
    root = path.parent
    while (root / "__init__.py").is_file():
        root = root.parent
    return importlib.import_module(".".join(path.relative_to(root).with_suffix("").parts))


def _configuration(gnc: str, build: str, contract: Contract) -> _Configuration:
    """Finds a configuration's claims, its members' parameters and, for Python, their classes.

    A component is instanced at most once, since its notebook's `parameters(scenario)` gives one
    tuple per component and so cannot tell two instances apart.

    Args:
        gnc: the configuration.
        build: the build, one of `BUILDS`.
        contract: the contract holding the configuration.

    Returns:
        What was found.

    Raises:
        ValueError: a component is instanced more than once; a member's component claims nothing
            or an ID the tree lacks; for the Python build, its notebook has no class named as the
            component; or the component has parameters and the notebook no `parameters`, naming
            what it looked for.
    """
    fpp_types.load(contract)
    model = configuration_model(gnc, contract=contract)
    instances = [m for group in members(model, gnc).values() for m in group]
    by_component: dict[str, list[str]] = {}
    for instance in instances:
        by_component.setdefault(instance.component, []).append(instance.name)
    for name, named in by_component.items():
        if len(named) > 1:
            raise ValueError(
                f"{name} is instanced more than once in {gnc}, as {named}, and its notebook's"
                " `parameters(scenario)` gives one tuple per component"
            )
    capabilities = {uid for name in by_component for uid in _claims(model, model.components[name])}
    found = []
    classes = []
    for instance in instances:
        component = model.components[instance.component]
        short = component.name.rsplit(".", 1)[-1]
        tuple_type = fpp_types.named(f"{component.name}Parameters")
        notebook = _notebook(component)
        if build == "python":
            cls = getattr(notebook, short, None)
            if not isinstance(cls, type):
                raise ValueError(f"{notebook.__file__} has no class {short} for {component.name}")
            classes.append(cls)
        function = None
        if tuple_type._fields:
            function = getattr(notebook, "parameters", None)
            if not callable(function):
                raise ValueError(
                    f"{notebook.__file__} defines no `parameters`, and {component.name} has the"
                    f" parameters {list(tuple_type._fields)}"
                )
        found.append(_Member(instance.name, tuple_type, function))
    return _Configuration(tuple(sorted(capabilities)), tuple(found), tuple(classes))


@dataclass(frozen=True)
class Mission:
    """A GNC configuration on a build and a vehicle, flown through scenarios and judged on rungs.

    Every lookup runs when the mission is built, so a mission that cannot fly fails in the cell
    that defines it. The F´ build's extension is not among them: only a case's `lab.Adapter` needs
    it.

    Attributes:
        vehicle: the vehicle every scenario flies, by its name in WiseDynamics' `VEHICLES`.
        gnc: the configuration, the name of its GNC sub-topology in the contract.
        build: the build it flies on, one of `BUILDS`.
        scenarios: the TST items to fly.
        rungs: the SRS items to judge, or None for every rung each flight reaches (see
            `requirements_tree.flight_rungs`).
        check: optionally, every way one case's run file fails the FSW's own per-case check,
            empty when it passes; each case's test asserts it is empty once the file is written.
        contract: the contract holding the configuration, the repository's by default; the F´
            build flies the configurations `fsw.codegen.deployment.fprime_configurations` selects.
    """

    vehicle: str
    gnc: str
    build: str
    scenarios: tuple[str, ...]
    rungs: tuple[str, ...] | None = None
    check: Callable[[Path], list[str]] | None = None
    contract: Contract = CONTRACT
    _found: _Configuration = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Look up the configuration and check every name against the requirements tree.

        Raises:
            ValueError: the vehicle, configuration or build is unknown; the F´ build is given a
                configuration it does not build; a lookup of `_configuration` fails; a rung or
                scenario is not in the tree; a scenario leaves the configuration no rung to judge;
                a rung is reached by none of the scenarios; or the rungs leave a scenario nothing
                to judge.
        """
        if self.vehicle not in VEHICLES:
            raise ValueError(f"no vehicle {self.vehicle!r}; known: {sorted(VEHICLES)}")
        known = configurations(contract=self.contract)
        if self.gnc not in known:
            raise ValueError(f"no configuration {self.gnc!r} in {self.contract.gnc}; known: {list(known)}")
        if self.build not in BUILDS:
            raise ValueError(f"no build {self.build!r}; known: {list(BUILDS)}")
        if self.build == "fprime" and self.gnc not in fprime_configurations(contract=self.contract):
            raise ValueError(
                f"the fprime build does not build {self.gnc!r}: a member's component has no F´"
                " component, no CMakeLists.txt beside its .fpp"
            )
        object.__setattr__(self, "_found", _configuration(self.gnc, self.build, self.contract))
        capabilities = self._found.capabilities
        for prefix, chosen in (("SRS", self.rungs or ()), ("TST", self.scenarios)):
            unknown = [uid for uid in chosen if uid not in requirements_tree.items(prefix)]
            if unknown:
                raise ValueError(f"no {prefix} item {unknown} in the requirements tree")
        reached: set[str] = set()
        for scenario_id in self.scenarios:
            rungs = requirements_tree.flight_rungs(scenario_id, capabilities)
            if not rungs:
                raise ValueError(f"{scenario_id} judges no rung under {self.gnc}'s capabilities {list(capabilities)}")
            reached.update(rungs)
        outside = sorted(set(self.rungs or ()) - reached)
        if outside:
            raise ValueError(f"no scenario of {self.scenarios} reaches the rungs {outside}")
        for scenario_id in self.scenarios:
            if not requirements_tree.flight_rungs(scenario_id, capabilities, self.rungs):
                raise ValueError(f"the rungs {self.rungs} leave {scenario_id} nothing to judge")

    def but(self, **changes: Any) -> "Mission":
        """This mission with some fields changed.

        Args:
            **changes: the fields to change.

        Returns:
            The new mission.
        """
        return replace(self, **changes)


def mission_tests(*missions: Mission) -> dict[str, type]:
    """The Monte Carlo tests of every mission: a class per vehicle, a test per FSW and scenario.

    A flight is a vehicle, a configuration, a build and a scenario; rungs only change what is
    judged. Two missions flying the same flight are a configuration error, stopped here before
    anything flies.

    Args:
        *missions: the missions.

    Returns:
        Each class by its name, `Test_<vehicle>`, holding `test_<gnc>_<build>_<definition>`.

    Raises:
        ValueError: two missions fly the same flight.
    """
    flown: set[tuple[str, str, str, str]] = set()
    for mission in missions:
        for scenario_id in mission.scenarios:
            flight = (mission.vehicle, mission.gnc, mission.build, scenario_id)
            if flight in flown:
                raise ValueError(
                    f"two missions fly {mission.gnc} on the {mission.build} build on"
                    f" {mission.vehicle} through {scenario_id}; judge more rungs by listing them"
                    " in one mission"
                )
            flown.add(flight)
    classes: dict[str, dict[str, Callable[..., None]]] = {}
    for mission in missions:
        name = f"Test_{mission.vehicle}"
        methods = classes.setdefault(name, {})
        for scenario_id in mission.scenarios:
            test = _scenario_test(mission, scenario_id)
            if test.__name__ in methods:
                raise ValueError(
                    f"{scenario_id} gives {mission.gnc} on the {mission.build} build on"
                    f" {mission.vehicle} the test name {test.__name__}, which another scenario's"
                    " flight already has"
                )
            test.__qualname__ = f"{name}.{test.__name__}"
            methods[test.__name__] = test
    return {
        name: type(name, (), {"_write_flight_json": _write_flight_json, **methods}) for name, methods in classes.items()
    }


@pytest.fixture(autouse=True)
def _write_flight_json(self: object, request: pytest.FixtureRequest, sim_test_directory: Path):
    """Record the facts of the flight this test flies, where the judge reads them.

    Autouse, so it runs before `sim_scenario` and a case that crashes in setup still leaves it.

    Args:
        self: the vehicle's test class.
        request: the fixture request, whose function carries the mission and scenario.
        sim_test_directory: the test's directory in the session.
    """
    _record_flight(request.function.mission, request.function.scenario_id, sim_test_directory)


def _record_flight(mission: Mission, scenario_id: str, directory: Path) -> None:
    """Record a flight's facts in its folder's `flight.json`, or skip an F´ flight not built.

    The write merges, so a `build` that an earlier case of the flight recorded survives it. An F´
    flight whose configuration's extension is absent removes the `flight.json` an earlier flight
    left, so the folder, left with no run of this flight, is judged and compared by nothing.

    Args:
        mission: the mission.
        scenario_id: the TST ID it flies.
        directory: the test's directory in the session.
    """
    if mission.build == "fprime" and not built(mission.gnc):
        (directory / "flight.json").unlink(missing_ok=True)
        pytest.skip(f"the F´ build of {mission.gnc} is absent; run `just fsw`")
    directory.mkdir(parents=True, exist_ok=True)
    _merge_json(
        directory / "flight.json",
        {
            "scenario": scenario_id,
            "fsw": {"gnc": mission.gnc, "build": mission.build},
            "capabilities": list(mission._found.capabilities),
            "rungs": None if mission.rungs is None else list(mission.rungs),
        },
    )


def _merge_json(path: Path, mapping: dict[str, Any]) -> None:
    """Overlay `mapping` on the JSON object in `path`, replacing the file atomically.

    The merged object is written to a temporary file beside `path` and moved into place, so a
    reader sees the previous file or the new one, never a half-written one.

    Args:
        path: the JSON file; a missing file is an empty object.
        mapping: the members to set.

    Raises:
        BaseException: whatever interrupted the write, after its temporary file is removed.
    """
    merged = {**(json.loads(path.read_text()) if path.exists() else {}), **mapping}
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump(merged, file)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _scenario_test(mission: Mission, scenario_id: str) -> Callable[..., None]:
    """The Monte Carlo test flying a mission through one scenario.

    The TST item's reference names the scenario's definition, its ground procedure, whose `sim_`
    marks say how it is flown; the test carries them and the mission's vehicle. The ground writes
    the case's parameter record beside its run file, as `run_<NNNN>.prm.json`, from each member's
    `parameters`, and the build is made on it: the Python build's `FrameRunner`, which is both
    sides, or the F´ build's `lab.Adapter`, with an `FprimeStation` on its pins as the radio edge.
    WiseDynamics' `FswHost` hosts the build. A `Ground` flies the procedure against the radio edge
    and records the run file. An exception the procedure raised is re-raised whole, and a procedure
    still waiting when the flight ends fails the case.

    Args:
        mission: the mission.
        scenario_id: the TST ID.

    Returns:
        The test, carrying `mission` and `scenario_id` for the judge.
    """
    reference = requirements_tree.items("TST")[scenario_id]["references"][0]
    definition = _definition(tuple(reference.items()), requirements_tree.ROOT)
    ground_period_s = next(
        (mark.args[0] for mark in definition.pytestmark if mark.name == "sim_ground_period_s"),
        None,
    )

    @pytest.mark.sim_vehicle(mission.vehicle)
    def test(
        self: object,
        sim_scenario: Any,
        sim_duration_s: float,
        sim_run_file: Callable[..., Path],
        sim_test_directory: Path,
        sim_case_index: int,
    ) -> None:
        """One case of the mission in the scenario writes its run file and passes the check.

        Args:
            self: the vehicle's test class.
            sim_scenario: the case's dispersed scenario.
            sim_duration_s: s, the case's simulated duration.
            sim_run_file: writes the case's run file.
            sim_test_directory: the test's directory in the session.
            sim_case_index: the case's number, which names its run file.

        Raises:
            ground.failure: the exception the procedure kept, re-raised whole in place of what
                the run raised.
            BaseException: what the run raised, when the procedure kept no exception.
        """
        record = run_path(sim_test_directory, sim_case_index).with_suffix(".prm.json")
        parameters.write(
            {
                member.instance: member.tuple_type() if member.parameters is None else member.parameters(sim_scenario)
                for member in mission._found.members
            },
            record,
        )
        if mission.build == "python":
            fsw = radio = FrameRunner(mission.gnc, record, mission._found.classes, contract=mission.contract)
        else:
            fsw = Adapter(mission.gnc, record, contract=mission.contract)
            radio = FprimeStation(fsw, fsw.dictionary)
        _merge_json(sim_test_directory / "flight.json", {"build": fsw.build})
        host = FswHost(fsw, sim_scenario.vehicle)
        # The simulation holds the ground, so a strong reference back would keep every case.
        scenario = weakref.ref(sim_scenario)
        ground = Ground(
            definition,
            radio,
            sim_scenario.vehicle.tracking(),
            lambda: scenario().stop_ground(),
            period_s=ground_period_s,
        )
        try:
            datasets = sim_scenario.run(host, fsw_fields={}, duration_s=sim_duration_s, ground=ground)
        except BaseException:
            if ground.failure is None:
                raise
            raise ground.failure from None
        ground.ensure_returned()
        datasets |= ground.telemetry_datasets()
        path = sim_run_file(datasets, attrs={"commands": json.dumps(ground.command_log)})
        problems = [] if mission.check is None else mission.check(path)
        if problems:
            pytest.fail("\n".join(problems), pytrace=False)

    test.pytestmark = [*test.pytestmark, *definition.pytestmark]
    test.__name__ = f"test_{mission.gnc}_{mission.build}_{definition.__name__}"
    test.mission = mission
    test.scenario_id = scenario_id
    return test


@functools.cache
def _definition(reference: tuple[tuple[str, str], ...], root: Path) -> Callable[[Ground], Coroutine[Any, Any, None]]:
    """The scenario definition a TST item's reference names.

    A module already loaded, or loading, from the referenced file supplies it, so a notebook can
    define a scenario that its own missions fly: the module pytest or the judge is importing, or in
    a kernel the notebook's own namespace. Otherwise the file is imported, registered before it
    runs so that a reference back to itself finds it there.

    Args:
        reference: the reference, its `path` relative to the repository and its `keyword`, the
            line `def <name>(` declaring the definition.
        root: the project root the reference's `path` is relative to.

    Returns:
        The definition, the scenario's ground procedure, whose `pytestmark` holds its `sim_` marks.

    Raises:
        ValueError: the file references a definition it has not yet defined, because a mission
            flying it comes first.
        BaseException: the file raised while importing; it is then not left registered, so a
            later lookup imports it afresh.
    """
    reference = dict(reference)
    path = (root / reference["path"]).resolve()
    name = re.match(r"def (\w+)\(", reference["keyword"]).group(1)
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if file and Path(file).resolve() == path and hasattr(module, name):
            return getattr(module, name)
    main = sys.modules.get("__main__")
    if getattr(main, "__file__", None) is None and hasattr(getattr(main, name, None), "pytestmark"):
        return getattr(main, name)
    module_name = f"_scenarios_{path}"
    if module_name in sys.modules:
        raise ValueError(f"{reference['path']} flies {name} before it defines it")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[module_name]
        raise
    return getattr(module, name)
