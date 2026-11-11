"""Missions: an FSW flown on a vehicle through chosen scenarios, judged on chosen rungs.

A mission lives outside the requirements tree. Its FSW claims the capabilities (SYS items) it
provides with `provides`; the mission picks the rungs (SRS items) to judge and the scenarios (TST
items) to fly. `mission_tests` turns missions into Monte Carlo tests for a notebook's
globals: a class per vehicle, holding a test per FSW and scenario, so each flight's runs have a
folder of their own.
"""

import functools
import importlib.util
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from wise_dynamics.basilisk.vehicles import VEHICLES

from gnc_cdh.basilisk import estimate_fields
from harness import requirements_tree


def provides(*capability_ids: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark an FSW builder with the capabilities it claims.

    Args:
        *capability_ids: SYS IDs, each of which must be in the requirements tree.

    Returns:
        A decorator setting the builder's `provides` to the IDs.

    Raises:
        ValueError: an ID names no SYS item.
    """
    unknown = [uid for uid in capability_ids if uid not in requirements_tree.items("SYS")]
    if unknown:
        raise ValueError(f"no capability {unknown} in the requirements tree")

    def mark(build: Callable[..., Any]) -> Callable[..., Any]:
        """Set the claim on the builder.

        Args:
            build: the FSW builder.

        Returns:
            The same builder.
        """
        build.provides = capability_ids
        return build

    return mark


@dataclass(frozen=True)
class Mission:
    """An FSW on a vehicle, flown through scenarios and judged on rungs.

    Attributes:
        vehicle: the vehicle every scenario flies, by its name in WiseDynamics' `VEHICLES`.
        fsw: builds the flight software for one case from its dispersed scenario, and claims its
            capabilities with `provides`.
        scenarios: the TST items to fly.
        rungs: the SRS items to judge, or None for every rung each flight reaches (see
            `requirements_tree.flight_rungs`).
        check: optionally, every way one case's run file fails the FSW's own per-case check,
            empty when it passes; each case's test asserts it is empty once the file is written.
    """

    vehicle: str
    fsw: Callable[[Any], Any]
    scenarios: tuple[str, ...]
    rungs: tuple[str, ...] | None = None
    check: Callable[[Path], list[str]] | None = None

    def __post_init__(self) -> None:
        """Check every name against the requirements tree.

        Raises:
            ValueError: the vehicle is unknown, the FSW claims nothing, a rung or scenario is not
                in the tree, a scenario leaves the FSW no rung to judge, a rung is reached by none
                of the scenarios, or the rungs leave a scenario nothing to judge.
        """
        if self.vehicle not in VEHICLES:
            raise ValueError(f"no vehicle {self.vehicle!r}; known: {sorted(VEHICLES)}")
        if not getattr(self.fsw, "provides", None):
            raise ValueError(f"{self.fsw.__name__} claims no capability; mark it with provides")
        for prefix, chosen in (("SRS", self.rungs or ()), ("TST", self.scenarios)):
            unknown = [uid for uid in chosen if uid not in requirements_tree.items(prefix)]
            if unknown:
                raise ValueError(f"no {prefix} item {unknown} in the requirements tree")
        reached: set[str] = set()
        for scenario_id in self.scenarios:
            rungs = requirements_tree.flight_rungs(scenario_id, self.fsw.provides)
            if not rungs:
                raise ValueError(
                    f"{scenario_id} judges no rung under {self.fsw.__name__}'s capabilities"
                    f" {sorted(self.fsw.provides)}"
                )
            reached.update(rungs)
        outside = sorted(set(self.rungs or ()) - reached)
        if outside:
            raise ValueError(f"no scenario of {self.scenarios} reaches the rungs {outside}")
        for scenario_id in self.scenarios:
            if not requirements_tree.flight_rungs(scenario_id, self.fsw.provides, self.rungs):
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

    A flight is a vehicle, an FSW and a scenario; rungs only change what is judged. Two missions
    flying the same flight are a configuration error, stopped here before anything flies.

    Args:
        *missions: the missions.

    Returns:
        Each class by its name, `Test_<vehicle>`, holding `test_<fsw>_<scenario>`.

    Raises:
        ValueError: two missions fly the same flight.
    """
    flown: set[tuple[str, str, str]] = set()
    for mission in missions:
        for scenario_id in mission.scenarios:
            flight = (mission.vehicle, mission.fsw.__name__, scenario_id)
            if flight in flown:
                raise ValueError(
                    f"two missions fly {mission.fsw.__name__} on {mission.vehicle} through"
                    f" {scenario_id}; judge more rungs by listing them in one mission"
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
                    f"{scenario_id} gives {mission.fsw.__name__} on {mission.vehicle} the test"
                    f" name {test.__name__}, which another scenario's flight already has"
                )
            test.__qualname__ = f"{name}.{test.__name__}"
            methods[test.__name__] = test
    return {
        name: type(name, (), {"_write_flight_json": _write_flight_json, **methods})
        for name, methods in classes.items()
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
    mission, scenario_id = request.function.mission, request.function.scenario_id
    sim_test_directory.mkdir(parents=True, exist_ok=True)
    (sim_test_directory / "flight.json").write_text(
        json.dumps(
            {
                "scenario": scenario_id,
                "capabilities": sorted(mission.fsw.provides),
                "rungs": None if mission.rungs is None else list(mission.rungs),
            }
        )
    )


def _scenario_test(mission: Mission, scenario_id: str) -> Callable[..., None]:
    """The Monte Carlo test flying a mission through one scenario.

    The TST item's reference names the scenario's definition, whose `sim_` marks say how it is
    flown; the test carries them and the mission's vehicle.

    Args:
        mission: the mission.
        scenario_id: the TST ID.

    Returns:
        The test, carrying `mission` and `scenario_id` for the judge.
    """
    reference = requirements_tree.items("TST")[scenario_id]["references"][0]
    definition = _definition(tuple(reference.items()), requirements_tree.ROOT)

    @pytest.mark.sim_vehicle(mission.vehicle)
    def test(
        self: object, sim_scenario: Any, sim_duration_s: float, sim_run_file: Callable[..., Path]
    ) -> None:
        """One case of the mission in the scenario writes its run file and passes the check.

        Args:
            self: the vehicle's test class.
            sim_scenario: the case's dispersed scenario.
            sim_duration_s: s, the case's simulated duration.
            sim_run_file: writes the case's run file.
        """
        fsw = mission.fsw(sim_scenario)
        datasets = sim_scenario.run(fsw, estimate_fields(fsw), duration_s=sim_duration_s)
        path = sim_run_file(datasets)
        problems = [] if mission.check is None else mission.check(path)
        if problems:
            pytest.fail("\n".join(problems), pytrace=False)

    test.pytestmark = [*test.pytestmark, *definition.pytestmark]
    test.__name__ = f"test_{mission.fsw.__name__}_{definition.__name__}"
    test.mission = mission
    test.scenario_id = scenario_id
    return test


@functools.cache
def _definition(reference: tuple[tuple[str, str], ...], root: Path) -> Callable[..., None]:
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
        The definition, whose `pytestmark` holds its `sim_` marks.

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
