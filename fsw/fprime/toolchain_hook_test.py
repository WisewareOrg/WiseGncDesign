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


def _requirements(root: Path, lines: list[str]) -> None:
    """Writes the framework's requirements file where the hook reads it.

    Args:
        root: the directory holding `lib/fprime/requirements.txt`.
        lines: the file's lines.
    """
    path = root / "lib" / "fprime" / "requirements.txt"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(lines) + "\n")


def _update(root: Path) -> dict[str, Any]:
    """Runs the hook on a root, as the build backend does.

    Args:
        root: the directory holding `lib/fprime/requirements.txt`.

    Returns:
        The metadata the hook updated.
    """
    spec = importlib.util.spec_from_file_location("toolchain_hook", HOOK)
    assert spec is not None and spec.loader is not None
    module = ModuleType(spec.name)
    spec.loader.exec_module(module)
    metadata: dict[str, Any] = {}
    module.ToolchainHook(str(root), {}).update(metadata)
    return metadata


def test_the_hook_declares_the_five_tools_at_the_versions_the_file_pins_and_nothing_else(
    tmp_path: Path,
):
    """Only the toolchain's lines become dependencies; other pins, comments and blanks are dropped.

    Args:
        tmp_path: the root holding a requirements file whose versions are not the repository's.
    """
    _requirements(
        tmp_path,
        [
            "# the framework's pins",
            "",
            "cmake==9.8.7",
            "fprime-fpy==0.0.1",
            "fprime-fpp==1.2.3",
            "fprime-gds==5.6.7",
            "fprime-tools==5.6.8",
            "fprime-yamcs==0.0.2",
            "ninja==2.3.4.5",
            "pytest==0.0.3",
        ],
    )

    metadata = _update(tmp_path)

    assert sorted(metadata["dependencies"]) == [
        "cmake==9.8.7",
        "fprime-fpp==1.2.3",
        "fprime-gds==5.6.7",
        "fprime-tools==5.6.8",
        "ninja==2.3.4.5",
    ]


def test_the_hook_refuses_a_file_missing_a_tool_naming_it(tmp_path: Path):
    """A requirements file without one of the five raises, naming the missing tool.

    Args:
        tmp_path: the root holding a requirements file without `fprime-gds`.
    """
    _requirements(
        tmp_path,
        [
            "cmake==9.8.7",
            "fprime-fpp==1.2.3",
            "fprime-tools==5.6.8",
            "ninja==2.3.4.5",
            "fprime-gds-extra==0.0.1",
        ],
    )

    with pytest.raises(ValueError, match="fprime-gds"):
        _update(tmp_path)


def test_the_hook_names_every_missing_tool(tmp_path: Path):
    """A file missing several of the five raises naming each of them.

    Args:
        tmp_path: the root holding a requirements file with only `cmake` and `ninja`.
    """
    _requirements(tmp_path, ["cmake==9.8.7", "ninja==2.3.4.5"])

    with pytest.raises(ValueError) as raised:
        _update(tmp_path)

    message = str(raised.value)
    assert all(tool in message for tool in ("fprime-tools", "fprime-fpp", "fprime-gds"))


def test_the_hook_declares_a_pin_spelled_otherwise_as_the_same_clean_requirement(tmp_path: Path):
    """An inline comment, name case, `_` for `-` and spaces around `==` do not change the pin.

    Args:
        tmp_path: the root holding a requirements file whose pins are spelled in variant ways.
    """
    _requirements(
        tmp_path,
        [
            "CMake == 9.8.7",
            "ninja==2.3.4.5  # the generator",
            "fprime_tools==5.6.8",
            "FPRIME-FPP==1.2.3",
            "fprime.gds==5.6.7",
        ],
    )

    metadata = _update(tmp_path)

    parsed = {
        canonicalize_name(r.name): str(r.specifier)
        for r in map(Requirement, metadata["dependencies"])
    }
    assert parsed == {
        "cmake": "==9.8.7",
        "ninja": "==2.3.4.5",
        "fprime-tools": "==5.6.8",
        "fprime-fpp": "==1.2.3",
        "fprime-gds": "==5.6.7",
    }


@pytest.mark.parametrize("unpinned", ["cmake>=9.8.7", "cmake~=9.8", "cmake"])
def test_the_hook_refuses_a_tool_that_is_not_pinned_with_an_equals_sign(
    tmp_path: Path, unpinned: str
):
    """A range or a bare name for a tool is not a pin, so the hook raises naming the tool.

    Args:
        tmp_path: the root holding a requirements file whose `cmake` line is not an `==` pin.
        unpinned: the `cmake` line.
    """
    _requirements(
        tmp_path,
        [
            unpinned,
            "fprime-fpp==1.2.3",
            "fprime-gds==5.6.7",
            "fprime-tools==5.6.8",
            "ninja==2.3.4.5",
        ],
    )

    with pytest.raises(ValueError, match="cmake"):
        _update(tmp_path)


def test_the_hook_tells_a_missing_requirements_file_to_run_just_sync(tmp_path: Path):
    """A root without the framework clone raises a message naming `just _sync`, not a bare OS error.

    Args:
        tmp_path: a root with no `lib/fprime/requirements.txt`.
    """
    with pytest.raises(ValueError, match="just _sync"):
        _update(tmp_path)
