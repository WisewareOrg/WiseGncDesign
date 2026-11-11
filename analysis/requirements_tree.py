"""The Doorstop requirements tree under `docs/requirements/`, read as plain YAML.

A SYS item is a capability, an SRS item one rung of its performance ladder, and a TST item a
scenario every capability above its linked rungs is flown through.
"""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / "docs" / "requirements"
SCENARIOS = "tests/scenarios/test_scenarios.py"


def items(prefix: str) -> dict[str, dict[str, Any]]:
    """Every active item of one document, by ID.

    Args:
        prefix: "SYS", "SRS" or "TST".

    Returns:
        The items.
    """
    found = {}
    for path in sorted((TREE / prefix.lower()).glob(f"{prefix}*.yml")):
        item = yaml.safe_load(path.read_text())
        if item.get("active", True):
            found[path.stem] = item
    return found


def parents(item: dict[str, Any]) -> list[str]:
    """The IDs an item links to.

    Args:
        item: the item.

    Returns:
        Its parents' IDs.
    """
    return [next(iter(link)) if isinstance(link, dict) else link for link in item["links"]]


def rungs(analyzer: str) -> list[str]:
    """The SRS items whose references name an analyzer's file.

    Args:
        analyzer: the analyzer's `__file__`.

    Returns:
        Their IDs.
    """
    relative = Path(analyzer).resolve().relative_to(ROOT).as_posix()
    return [
        uid
        for uid, item in items("SRS").items()
        if any(reference["path"] == relative for reference in item.get("references") or [])
    ]


def limit(requirement_id: str, name: str) -> float:
    """One limit of one SRS item.

    Args:
        requirement_id: the SRS ID.
        name: "x", "p" or "c".

    Returns:
        The limit.
    """
    return float(items("SRS")[requirement_id][name])


def campaign_name(scenario_id: str, capability_id: str) -> str:
    """The generated Monte Carlo test flying one capability through one scenario.

    Args:
        scenario_id: the TST ID.
        capability_id: the SYS ID.

    Returns:
        The test's function name.
    """
    return f"test_{scenario_id.lower()}_{capability_id.lower()}"


def campaigns() -> list[tuple[str, str]]:
    """Every (scenario, capability) pair the tree links, through the rungs between them.

    Returns:
        (TST ID, SYS ID) pairs.
    """
    requirements = items("SRS")
    pairs = []
    for scenario_id, scenario in items("TST").items():
        for requirement_id in parents(scenario):
            for capability_id in parents(requirements[requirement_id]):
                if (scenario_id, capability_id) not in pairs:
                    pairs.append((scenario_id, capability_id))
    return pairs


def claiming_tests(requirement_id: str) -> list[str]:
    """The node IDs of the generated tests whose runs judge one rung.

    Args:
        requirement_id: the SRS ID.

    Returns:
        One node ID per scenario linked to the rung, flying the rung's capability.
    """
    capabilities = parents(items("SRS")[requirement_id])
    return [
        f"{SCENARIOS}::{campaign_name(scenario_id, capability_id)}"
        for scenario_id, scenario in items("TST").items()
        if requirement_id in parents(scenario)
        for capability_id in capabilities
    ]
