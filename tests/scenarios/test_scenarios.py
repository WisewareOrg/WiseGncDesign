"""One Monte Carlo test per (scenario, capability) pair the requirements tree links.

A TST item is a scenario: its `scenario` and `runs` attributes say what flies and how many cases.
Every capability (SYS item) above the rungs it is linked to is flown through it. A capability's
reference names the function that builds its flight software; that function's module also provides
`estimate_fields`.
"""

import importlib
import re
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest

from requirements_tree import campaign_name, campaigns, items


def _campaign(scenario_id: str, capability_id: str) -> Callable[..., None]:
    """The Monte Carlo test flying one capability through one scenario.

    Args:
        scenario_id: the TST ID.
        capability_id: the SYS ID.

    Returns:
        The test function.
    """
    scenario = items("TST")[scenario_id]
    reference = items("SYS")[capability_id]["references"][0]
    module_name = Path(reference["path"]).with_suffix("").relative_to("algorithms")
    module = importlib.import_module(".".join(module_name.parts))
    build = getattr(module, re.match(r"def (\w+)\(", reference["keyword"]).group(1))

    @pytest.mark.sim_runs(scenario["runs"])
    @pytest.mark.sim_scenario(scenario["scenario"])
    def test(sim_scenario: Any, sim_duration_s: float, sim_run_file: Callable[..., Path]) -> None:
        """One case of the capability in the scenario writes its run file.

        Args:
            sim_scenario: the case's dispersed scenario.
            sim_duration_s: s, the case's simulated duration.
            sim_run_file: writes the case's run file.
        """
        fsw = build(sim_scenario)
        datasets = sim_scenario.run(fsw, module.estimate_fields(fsw), duration_s=sim_duration_s)
        sim_run_file(datasets, {"versions_wise_gnc_design": version("wise-gnc-design")})

    test.__name__ = test.__qualname__ = campaign_name(scenario_id, capability_id)
    return test


for _scenario_id, _capability_id in campaigns():
    globals()[campaign_name(_scenario_id, _capability_id)] = _campaign(_scenario_id, _capability_id)
