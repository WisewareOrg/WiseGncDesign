"""The toolchain metadata hook declares the tools at the versions the framework's requirements pin.

The hook names five tools and never their versions, so each test writes a requirements file whose
versions differ from the repository's real ones. The hook is loaded by path: `fsw/fprime` is a
package of its own for the build backend, not an import path.
"""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

HOOK = Path(__file__).parent / "toolchain_hook.py"
"""The hook module, beside this test."""

PINNED = {
    "cmake": "9.8.7",
    "fprime-fpp": "1.2.3",
    "fprime-gds": "5.6.7",
    "fprime-tools": "5.6.8",
    "ninja": "2.3.4.5",
}
"""The five tools at versions that are not the repository's real ones."""


def pin_lines(**spelled: str) -> list[str]:
    """List the five tools' `==` lines, replacing the line of any tool given by its name.

    Args:
        **spelled: replacement lines keyed by tool name with `-` written `_`.

    Returns:
        One line per tool in `PINNED`.
    """
    return [spelled.get(tool.replace("-", "_"), f"{tool}=={ver}") for tool, ver in PINNED.items()]


class TestToolchainHook:
    """The hook run on a root holding a framework requirements file."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        """Keep the root and load the hook module.

        Args:
            tmp_path: the root the hook reads `lib/fprime/requirements.txt` from.
        """
        self.root = tmp_path
        spec = importlib.util.spec_from_file_location("toolchain_hook", HOOK)
        assert spec is not None, f"cannot load {HOOK}"
        assert spec.loader is not None, f"{HOOK} has no loader"
        self.module = ModuleType(spec.name)
        spec.loader.exec_module(self.module)

    def write_requirements(self, lines: list[str]) -> None:
        """Write the framework's requirements file where the hook reads it.

        Args:
            lines: the file's lines.
        """
        path = self.root / "lib" / "fprime" / "requirements.txt"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(lines) + "\n")

    def update(self) -> dict[str, Any]:
        """Run the hook on the root, as the build backend does.

        Returns:
            The metadata the hook updated.
        """
        metadata: dict[str, Any] = {}
        self.module.ToolchainHook(str(self.root), {}).update(metadata)
        return metadata

    def test_only_the_five_tools_become_dependencies(self):
        """Other pins, comments and blanks in the file are dropped."""
        self.write_requirements(
            ["# the framework's pins", "", "fprime-fpy==0.0.1", *pin_lines(), "pytest==0.0.3"]
        )

        dependencies = self.update()["dependencies"]

        assert sorted(dependencies) == sorted(f"{t}=={v}" for t, v in PINNED.items()), (
            f"dependencies {dependencies} are not exactly the five tools at the file's versions"
        )

    def test_a_decoy_sharing_a_tools_prefix_is_not_that_tool(self):
        """A missing tool raises naming it, though a longer name starts with it."""
        self.write_requirements(
            [line for line in pin_lines() if not line.startswith("fprime-gds")]
            + ["fprime-gds-extra==0.0.1"]
        )

        with pytest.raises(ValueError, match="fprime-gds"):
            self.update()

    def test_every_missing_tool_is_named(self):
        """A file missing several of the five names each of them, not only the first."""
        self.write_requirements(["cmake==9.8.7", "ninja==2.3.4.5"])

        with pytest.raises(ValueError) as raised:
            self.update()

        message = str(raised.value)
        for tool in ("fprime-tools", "fprime-fpp", "fprime-gds"):
            assert tool in message, f"the message {message!r} does not name the missing {tool}"

    def test_a_pin_spelled_otherwise_is_the_same_clean_requirement(self):
        """A comment, name case, `_` or `.` for `-`, and spaces around `==` do not change the pin."""
        self.write_requirements(
            pin_lines(
                cmake="CMake == 9.8.7",
                ninja="ninja==2.3.4.5  # the generator",
                fprime_tools="fprime_tools==5.6.8",
                fprime_fpp="FPRIME-FPP==1.2.3",
                fprime_gds="fprime.gds==5.6.7",
            )
        )

        dependencies = self.update()["dependencies"]

        parsed = {
            canonicalize_name(r.name): str(r.specifier) for r in map(Requirement, dependencies)
        }
        assert parsed == {tool: f"=={ver}" for tool, ver in PINNED.items()}, (
            f"dependencies {dependencies} are not the five tools at the file's versions"
        )

    @pytest.mark.parametrize("unpinned", ["cmake>=9.8.7", "cmake~=9.8", "cmake"])
    def test_a_tool_not_pinned_with_an_equals_sign_is_refused(self, unpinned: str):
        """A range or a bare name for a tool is not a pin, so the hook raises naming the tool.

        Args:
            unpinned: the `cmake` line.
        """
        self.write_requirements(pin_lines(cmake=unpinned))

        with pytest.raises(ValueError, match="cmake"):
            self.update()

    def test_a_missing_requirements_file_says_to_run_just_sync(self):
        """A root without the framework clone raises a message naming `just _sync`."""
        with pytest.raises(ValueError, match="just _sync"):
            self.update()
