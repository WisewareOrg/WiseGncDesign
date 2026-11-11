"""Missions: an FSW flown on a vehicle through chosen scenarios, judged on chosen rungs.

A mission lives outside the requirements tree. Its FSW claims the capabilities (SYS items) it
provides with `provides`; the mission picks the rungs (SRS items) to judge and the scenarios (TST
items) to fly. `mission_tests` turns a mission into one Monte Carlo test per scenario, for a
notebook to put in its globals.
"""

import re
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
        name: an identifier, used in the generated tests' names.
        vehicle: the vehicle class every scenario must fly. Scenarios build their own vehicle
            today, so this is checked against the scenario rather than chosen.
        fsw: builds the flight software for one case from its dispersed scenario, and claims its
            capabilities with `provides`.
        rungs: the SRS items to judge.
        scenarios: the TST items to fly.
    """

    name: str
    vehicle: str
    fsw: Callable[[Any], Any]
    rungs: tuple[str, ...]
    scenarios: tuple[str, ...]

    def __post_init__(self) -> None:
        """Check every name against the requirements tree.

        Raises:
            ValueError: a name is not an identifier, the FSW claims nothing, or a rung or
                scenario is not in the tree.
        """
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError(f"mission name {self.name!r} is not a lowercase identifier")
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


def mission_tests(mission: Mission) -> dict[str, Callable[..., None]]:
    """One Monte Carlo test per scenario the mission flies.

    Args:
        mission: the mission.

    Returns:
        Each test by its name, `test_<mission>_<scenario>`.
    """
    tests = {}
    for scenario_id in mission.scenarios:
        test = _scenario_test(mission, scenario_id)
        tests[test.__name__] = test
    return tests


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
    def test(sim_scenario: Any, sim_duration_s: float, sim_run_file: Callable[..., Path]) -> None:
        """One case of the mission in the scenario writes its run file.

        Args:
            sim_scenario: the case's dispersed scenario.
            sim_duration_s: s, the case's simulated duration.
            sim_run_file: writes the case's run file.
        """
        flown = type(sim_scenario.vehicle).__name__
        assert flown == mission.vehicle, f"the scenario flies a {flown}, not a {mission.vehicle}"
        fsw = mission.fsw(sim_scenario)
        fields = sys.modules[mission.fsw.__module__].estimate_fields(fsw)
        datasets = sim_scenario.run(fsw, fields, duration_s=sim_duration_s)
        sim_run_file(
            datasets,
            {
                "versions_wise_gnc_design": version("wise-gnc-design"),
                "mission": mission.name,
                "scenario_item": scenario_id,
                "capabilities": ",".join(mission.fsw.provides),
            },
        )

    test.__name__ = test.__qualname__ = f"test_{mission.name}_{scenario['scenario']}"
    test.mission = mission
    test.scenario_id = scenario_id
    return test
