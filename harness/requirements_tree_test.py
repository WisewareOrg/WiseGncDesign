"""The requirements tree's reading: the rungs a flight judges.

The tree is written in a temporary project with the shared item writer, and read at the root the
test points `requirements_tree.ROOT` to.
"""

from pathlib import Path

import pytest

from harness import requirements_tree
from harness.conftest import write_item


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tree in `tmp_path`: two capabilities, four rungs and a scenario linking three of them.

    SYS901 owns SRS901, SRS902 and SRS904; SYS902 owns SRS903. TST901 links SRS901, SRS902 and
    SRS903.

    Args:
        tmp_path: the test's directory.
        monkeypatch: points `requirements_tree.ROOT` at it.

    Returns:
        The project root holding the tree.
    """
    for uid in ("SYS901", "SYS902"):
        write_item(tmp_path, "sys", uid, links=[])
    for uid, parent in (
        ("SRS901", "SYS901"),
        ("SRS902", "SYS901"),
        ("SRS903", "SYS902"),
        ("SRS904", "SYS901"),
    ):
        write_item(tmp_path, "srs", uid, links=[{parent: "stamp"}])
    write_item(
        tmp_path,
        "tst",
        "TST901",
        links=[{uid: "stamp"} for uid in ("SRS901", "SRS902", "SRS903")],
    )
    monkeypatch.setattr(requirements_tree, "ROOT", tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    ("claims", "only", "expected"),
    [
        (["SYS901"], None, ("SRS901", "SRS902")),
        (["SYS902"], None, ("SRS903",)),
        (["SYS902", "SYS901"], None, ("SRS901", "SRS902", "SRS903")),
        (["SYS901"], ["SRS902", "SRS903", "SRS904"], ("SRS902",)),
    ],
    ids=["one-capability", "other-capability", "both-capabilities", "filtered"],
)
def test_a_flight_judges_the_rungs_the_scenario_links_the_capabilities_own_and_the_filter_names(
    tree: Path, claims: list[str], only: list[str] | None, expected: tuple[str, ...]
) -> None:
    """TST901 links SRS901-3; a capability owns its rungs; the filter keeps only those it names.

    Args:
        tree: the tree.
        claims: the capabilities claimed.
        only: the filter, or None.
        expected: the rungs judged.
    """
    assert requirements_tree.flight_rungs("TST901", claims, only) == expected
