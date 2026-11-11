"""The Doorstop requirements tree under `docs/requirements/`, read as plain YAML.

A SYS item is a capability, an SRS item one rung of performance any number of capabilities claim,
and a TST item a scenario that evaluates the rungs it links to. Missions, outside the tree, choose
what flies.
"""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / "docs" / "requirements"


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
