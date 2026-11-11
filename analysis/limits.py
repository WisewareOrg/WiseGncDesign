"""A requirement's limits, read from its item in the Doorstop tree at `docs/requirements/srs/`."""

from pathlib import Path

import yaml

SRS = Path(__file__).resolve().parents[1] / "docs" / "requirements" / "srs"


def limit(requirement_id: str, name: str) -> float:
    """One limit of one requirement.

    Args:
        requirement_id: the requirement's ID, e.g. "SRS001".
        name: the item attribute holding the limit: "x", "p" or "c".

    Returns:
        The limit.
    """
    item = yaml.safe_load((SRS / f"{requirement_id}.yml").read_text())
    return float(item[name])
