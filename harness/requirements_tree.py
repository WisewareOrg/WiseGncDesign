"""The Doorstop requirements tree under `docs/requirements/`, read as plain YAML.

A SYS item is a capability, an SRS item one rung of performance any number of capabilities claim,
and a TST item a scenario that evaluates the rungs it links to. Missions, outside the tree, choose
what flies.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

# The repository root; the judging plugin sets it to pytest's rootdir.
ROOT = Path(__file__).resolve().parents[1]


def items(prefix: str) -> dict[str, dict[str, Any]]:
    """Every active item of one document, by ID.

    Args:
        prefix: "SYS", "SRS" or "TST".

    Returns:
        The items.
    """
    tree = ROOT / "docs" / "requirements" / prefix.lower()
    found = {}
    for path in sorted(tree.glob(f"{prefix}*.yml")):
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


def flight_rungs(
    scenario: str,
    capabilities: Iterable[str],
    rungs: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """The rungs a flight judges: the scenario's rungs under the capabilities, within the filter.

    Args:
        scenario: the TST ID.
        capabilities: the SYS IDs the flight software claims.
        rungs: the SRS IDs to judge, or None for every rung the flight reaches.

    Returns:
        The SRS IDs, sorted.
    """
    claimed = set(capabilities)
    linked = set(parents(items("TST")[scenario]))
    owned = {uid for uid, item in items("SRS").items() if claimed & set(parents(item))}
    reached = linked & owned
    if rungs is not None:
        reached &= set(rungs)
    return tuple(sorted(reached))
