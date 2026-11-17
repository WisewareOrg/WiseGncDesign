"""Fixtures shared by the harness tests."""

from collections.abc import Callable

import pytest


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
