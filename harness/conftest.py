"""Fixtures shared by the harness tests."""

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml


def write_item(root: Path, document: str, uid: str, **fields: object) -> None:
    """Write one item of the requirements tree.

    Args:
        root: the project root.
        document: "sys", "srs" or "tst".
        uid: the item's ID.
        **fields: the item's fields beyond `active` and `header`.
    """
    folder = root / "docs" / "requirements" / document
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{uid}.yml").write_text(yaml.safe_dump({"active": True, "header": uid, **fields}))


@pytest.fixture
def fly_in_a_subprocess() -> Callable[..., pytest.RunResult]:
    """Run a pytester project's tests in a subprocess whose tree root is the project.

    Returns:
        A function taking the pytester and more pytest arguments, returning the result.
    """

    def fly(project: pytest.Pytester, *args: str) -> pytest.RunResult:
        """Run the project's tests.

        Args:
            project: the pytester project, with its tree written.
            *args: more pytest arguments.

        Returns:
            The result; the project keeps no conftest after it.
        """
        conftest = project.makeconftest(
            "from pathlib import Path\n\n"
            "from harness import requirements_tree\n\n"
            "requirements_tree.ROOT = Path(__file__).parent\n"
        )
        try:
            return project.runpytest_subprocess("-p", "no:cacheprovider", *args)
        finally:
            conftest.unlink()

    return fly
