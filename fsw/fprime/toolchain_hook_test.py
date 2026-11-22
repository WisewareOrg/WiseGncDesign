"""The toolchain metadata hook declares the tools at the versions the framework's requirements pin.

The hook names five tools and never their versions, so each test feeds it requirements whose
versions differ from the repository's real ones, and the fetch is replaced by a stand-in. The hook
is loaded by path: `fsw/fprime` is a package of its own for the build backend, not an import path.
"""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn
from urllib.error import URLError

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


class FakeResponse:
    """A stand-in for the response `urlopen` returns, usable as a context manager."""

    def __init__(self, body: str):
        """Hold the body the response reads.

        Args:
            body: the text of the fetched file.
        """
        self.body = body

    def __enter__(self) -> "FakeResponse":
        """Enter the context.

        Returns:
            This response.
        """
        return self

    def __exit__(self, *exc: object) -> None:
        """Leave the context, suppressing nothing.

        Args:
            *exc: the exception triple, ignored.
        """

    def read(self) -> bytes:
        """Read the body.

        Returns:
            The body encoded as the network delivers it.
        """
        return self.body.encode()


class TestToolchainHook:
    """The hook's `toolchain` function and its `update` method, loaded from the file by path."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Load the hook module."""
        spec = importlib.util.spec_from_file_location("toolchain_hook", HOOK)
        assert spec is not None, f"cannot load {HOOK}"
        assert spec.loader is not None, f"{HOOK} has no loader"
        self.module = ModuleType(spec.name)
        spec.loader.exec_module(self.module)

    def declared(self, lines: list[str]) -> list[str]:
        """Run `toolchain` on a requirements file made of the lines.

        Args:
            lines: the file's lines.

        Returns:
            The dependencies `toolchain` declares.
        """
        return self.module.toolchain("\n".join(lines) + "\n")

    def run_update(self, root: Path, fetch: Callable[[str], Any]) -> dict[str, Any]:
        """Run `update` on a root whose `fprime-tag` holds `v9.9.9`, with `urlopen` replaced.

        Args:
            root: the directory to write `fprime-tag` into.
            fetch: called with the URL in place of `urlopen`; returns the response or raises.

        Returns:
            The metadata `update` filled.
        """
        (root / "fprime-tag").write_text("v9.9.9\n")
        self.module.urlopen = lambda url, timeout: fetch(url)
        metadata: dict[str, Any] = {}
        self.module.ToolchainHook(str(root), {}).update(metadata)
        return metadata

    def test_only_the_five_tools_become_dependencies(self):
        """Other pins, comments and blanks in the file are dropped."""
        dependencies = self.declared(
            ["# the framework's pins", "", "fprime-fpy==0.0.1", *pin_lines(), "pytest==0.0.3"]
        )

        assert sorted(dependencies) == sorted(f"{t}=={v}" for t, v in PINNED.items()), (
            f"dependencies {dependencies} are not exactly the five tools at the file's versions"
        )

    def test_a_decoy_sharing_a_tools_prefix_is_not_that_tool(self):
        """A missing tool raises naming it, though a longer name starts with it."""
        lines = [line for line in pin_lines() if not line.startswith("fprime-gds")]

        with pytest.raises(ValueError, match="fprime-gds"):
            self.declared([*lines, "fprime-gds-extra==0.0.1"])

    def test_every_missing_tool_is_named(self):
        """A file missing several of the five names each of them, not only the first."""
        with pytest.raises(ValueError) as raised:
            self.declared(["cmake==9.8.7", "ninja==2.3.4.5"])

        message = str(raised.value)
        for tool in ("fprime-tools", "fprime-fpp", "fprime-gds"):
            assert tool in message, f"the message {message!r} does not name the missing {tool}"

    def test_a_pin_spelled_otherwise_is_the_same_clean_requirement(self):
        """A comment, name case, `_` or `.` for `-`, and spaces around `==` leave the pin as is."""
        dependencies = self.declared(
            pin_lines(
                cmake="CMake == 9.8.7",
                ninja="ninja==2.3.4.5  # the generator",
                fprime_tools="fprime_tools==5.6.8",
                fprime_fpp="FPRIME-FPP==1.2.3",
                fprime_gds="fprime.gds==5.6.7",
            )
        )

        parsed = {
            canonicalize_name(r.name): str(r.specifier) for r in map(Requirement, dependencies)
        }
        assert parsed == {tool: f"=={ver}" for tool, ver in PINNED.items()}, (
            f"dependencies {dependencies} are not the five tools at the file's versions"
        )

    def test_a_pin_with_an_environment_marker_is_still_that_pin(self):
        """A tool line carrying a `; marker` is declared at the version it pins."""
        dependencies = self.declared(
            pin_lines(fprime_fpp='fprime.fpp==1.2.3; sys_platform == "linux"')
        )

        parsed = {
            canonicalize_name(r.name): str(r.specifier) for r in map(Requirement, dependencies)
        }
        assert parsed["fprime-fpp"] == "==1.2.3", (
            f"dependencies {dependencies} do not pin fprime-fpp at the marked line's version"
        )

    @pytest.mark.parametrize("unpinned", ["cmake>=9.8.7", "cmake~=9.8", "cmake"])
    def test_a_tool_not_pinned_with_an_equals_sign_is_refused(self, unpinned: str):
        """A range or a bare name for a tool is not a pin, so the hook raises naming the tool.

        Args:
            unpinned: the `cmake` line.
        """
        with pytest.raises(ValueError, match="cmake"):
            self.declared(pin_lines(cmake=unpinned))

    def test_update_fetches_the_requirements_at_the_tag_in_the_tag_file(self, tmp_path: Path):
        """The URL fetched carries the tag `fprime-tag` holds, newline stripped.

        Args:
            tmp_path: the root holding `fprime-tag`.
        """
        urls: list[str] = []

        def fetch(url: str) -> FakeResponse:
            """Record the URL and answer with the five tools' pins.

            Args:
                url: the URL the hook fetches.

            Returns:
                A response holding the pins.
            """
            urls.append(url)
            return FakeResponse("\n".join(pin_lines()))

        self.run_update(tmp_path, fetch)

        assert urls == ["https://raw.githubusercontent.com/nasa/fprime/v9.9.9/requirements.txt"], (
            f"fetched {urls}, not the requirements.txt at tag v9.9.9"
        )

    def test_update_assigns_the_fetched_tools_as_the_dependencies(self, tmp_path: Path):
        """`dependencies` is the `toolchain` of the fetched text.

        Args:
            tmp_path: the root holding `fprime-tag`.
        """
        body = "\n".join([*pin_lines(), "pytest==0.0.3"])

        metadata = self.run_update(tmp_path, lambda url: FakeResponse(body))

        assert metadata.get("dependencies") == [
            f"{tool}=={PINNED[tool]}" for tool in self.module.TOOLS
        ], f"dependencies {metadata.get('dependencies')} are not the five tools in TOOLS order"

    def test_update_names_the_url_when_the_fetch_fails(self, tmp_path: Path):
        """A network error raises a ValueError naming the URL it could not fetch.

        Args:
            tmp_path: the root holding `fprime-tag`.
        """

        def fetch(url: str) -> NoReturn:
            """Fail as an unreachable network does.

            Args:
                url: the URL the hook fetches.

            Raises:
                URLError: always.
            """
            raise URLError("no route to host")

        with pytest.raises(ValueError, match="nasa/fprime/v9.9.9/requirements.txt"):
            self.run_update(tmp_path, fetch)
