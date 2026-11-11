"""Missions: an FSW flown on a vehicle through chosen scenarios, judged on chosen rungs.

A mission lives outside the requirements tree. Its FSW claims the capabilities (SYS items) it
provides with `provides`; the mission picks the rungs (SRS items) to judge and the scenarios (TST
items) to fly. `mission_tests` turns missions into Monte Carlo tests for a notebook's
globals: a class per vehicle, holding a test per FSW and scenario, so each flight's runs have a
folder of their own.
"""

import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest

from requirements_tree import items


def provides(*capability_ids: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark an FSW builder with the capabilities it claims.

    Args:
        *capability_ids: SYS IDs, each of which must be in the requirements tree.

    Returns:
        A decorator setting the builder's `provides` to the IDs.

    Raises:
        ValueError: an ID names no SYS item.
    """
    unknown = [uid for uid in capability_ids if uid not in items("SYS")]
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
        rungs: the SRS items to judge.
        scenarios: the TST items to fly.
    """

    vehicle: str
    fsw: Callable[[Any], Any]
    rungs: tuple[str, ...]
    scenarios: tuple[str, ...]

    def __post_init__(self) -> None:
        """Check every name against the requirements tree.

        Raises:
            ValueError: the vehicle is unknown, the FSW claims nothing, or a rung or scenario
                is not in the tree.
        """
        from wise_dynamics.basilisk.vehicles import VEHICLES

        if self.vehicle not in VEHICLES:
            raise ValueError(f"no vehicle {self.vehicle!r}; known: {sorted(VEHICLES)}")
        if not getattr(self.fsw, "provides", None):
            raise ValueError(f"{self.fsw.__name__} claims no capability; mark it with provides")
        for prefix, chosen in (("SRS", self.rungs), ("TST", self.scenarios)):
            unknown = [uid for uid in chosen if uid not in items(prefix)]
            if unknown:
                raise ValueError(f"no {prefix} item {unknown} in the requirements tree")

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
    classes: dict[str, dict[str, Callable[..., None]]] = {}
    for mission in missions:
        name = f"Test_{mission.vehicle}"
        methods = classes.setdefault(name, {})
        for scenario_id in mission.scenarios:
            test = _scenario_test(mission, scenario_id)
            if test.__name__ in methods:
                raise ValueError(
                    f"two missions fly {mission.fsw.__name__} on {mission.vehicle} through"
                    f" {scenario_id}; judge more rungs by listing them in one mission"
                )
            test.__qualname__ = f"{name}.{test.__name__}"
            methods[test.__name__] = test
    return {name: type(name, (), methods) for name, methods in classes.items()}


def _scenario_test(mission: Mission, scenario_id: str) -> Callable[..., None]:
    """The Monte Carlo test flying a mission through one scenario.

    The FSW's module provides `estimate_fields`, which names what to record.

    Args:
        mission: the mission.
        scenario_id: the TST ID.

    Returns:
        The test, carrying `mission` and `scenario_id` for the judge.
    """
    scenario = items("TST")[scenario_id]

    @pytest.mark.sim_runs(scenario["runs"])
    @pytest.mark.sim_scenario(scenario["scenario"])
    @pytest.mark.sim_vehicle(mission.vehicle)
    def test(
        self: object, sim_scenario: Any, sim_duration_s: float, sim_run_file: Callable[..., Path]
    ) -> None:
        """One case of the mission in the scenario writes its run file.

        Args:
            self: the vehicle's test class.
            sim_scenario: the case's dispersed scenario.
            sim_duration_s: s, the case's simulated duration.
            sim_run_file: writes the case's run file.
        """
        fsw = mission.fsw(sim_scenario)
        fields = sys.modules[mission.fsw.__module__].estimate_fields(fsw)
        datasets = sim_scenario.run(fsw, fields, duration_s=sim_duration_s)
        sim_run_file(
            datasets,
            {
                "versions_wise_gnc_design": version("wise-gnc-design"),
                "vehicle": mission.vehicle,
                "scenario_item": scenario_id,
                "capabilities": ",".join(mission.fsw.provides),
            },
        )

    test.__name__ = f"test_{mission.fsw.__name__}_{scenario['scenario']}"
    test.mission = mission
    test.scenario_id = scenario_id
    return test
