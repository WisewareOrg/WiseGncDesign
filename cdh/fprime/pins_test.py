"""The F´ build tools this project pins agree with the pins of the F´ framework clone.

`just _sync` clones the framework at `fprime_tag`; its `requirements.txt` fixes the tool versions
that tag was released with.
"""

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "cdh" / "fprime" / "lib" / "fprime" / "requirements.txt"

TOOLS = ("cmake", "ninja", "fprime-tools", "fprime-fpp")
"""The tools whose version F´ fixes and this project must not move."""


def _exact_pins(lines: list[str]) -> dict[str, str]:
    """Map each pinned tool to its `==` version.

    Args:
        lines: Requirement specifiers, one per entry; blanks and comments are skipped.

    Returns:
        The version of each tool in `TOOLS` that is `==`-pinned. A tool that is absent or not
        pinned by a single `==` is left out.
    """
    pins = {}
    for line in lines:
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        req = Requirement(text)
        name = canonicalize_name(req.name)
        specs = list(req.specifier)
        if name in TOOLS and len(specs) == 1 and specs[0].operator == "==":
            pins[name] = specs[0].version
    return pins


def divergences(group: list[str], framework: list[str]) -> list[str]:
    """List the tools that are not pinned alike in the project and in the framework.

    Args:
        group: The project's `fprime` dependency group.
        framework: The lines of the framework's `requirements.txt`.

    Returns:
        One message per tool that either side leaves unpinned, or that the sides pin apart.
    """
    ours, theirs = _exact_pins(group), _exact_pins(framework)
    found = []
    for tool in TOOLS:
        if tool not in ours:
            found.append(f"{tool} is not ==-pinned in the fprime group")
        elif tool not in theirs:
            found.append(f"{tool} is not ==-pinned in the framework's requirements.txt")
        elif ours[tool] != theirs[tool]:
            found.append(f"{tool}: project {ours[tool]}, framework {theirs[tool]}")
    return found


def test_the_project_pins_the_f_prime_tools_at_the_framework_versions():
    """Each tool is `==`-pinned in the `fprime` group at the version the framework clone pins."""
    assert REQUIREMENTS.is_file(), f"{REQUIREMENTS} is absent: run `just _sync` to clone F´"
    group = tomllib.loads((ROOT / "pyproject.toml").read_text())["dependency-groups"]["fprime"]
    framework = REQUIREMENTS.read_text().splitlines()
    assert divergences(group, framework) == []


FRAMEWORK = ["cmake==3.26.0", "ninja==1.11.1.4", "fprime-tools==4.4.0", "fprime-fpp==3.4.0"]
PROJECT = ["cmake==3.26.0", "fprime-fpp==3.4.0", "fprime-tools==4.4.0", "ninja==1.11.1.4"]


def test_a_tool_pinned_to_another_version_diverges():
    """A project pin that differs from the framework's is reported, naming the tool."""
    wrong = [p.replace("fprime-tools==4.4.0", "fprime-tools==4.5.0") for p in PROJECT]
    assert divergences(wrong, FRAMEWORK) == ["fprime-tools: project 4.5.0, framework 4.4.0"]


def test_a_tool_that_is_not_exactly_pinned_diverges():
    """A range, or a tool missing from either side, is reported."""
    ranged = [p.replace("cmake==3.26.0", "cmake>=3.26.0") for p in PROJECT]
    assert divergences(ranged, FRAMEWORK) == ["cmake is not ==-pinned in the fprime group"]
    assert divergences(PROJECT, FRAMEWORK[:3]) == [
        "fprime-fpp is not ==-pinned in the framework's requirements.txt"
    ]


def test_a_spelling_variant_of_the_same_pin_agrees():
    """Name case, `_` for `-`, spacing, markers and comments do not read as divergence."""
    variant = [
        "CMake == 3.26.0",
        "Ninja==1.11.1.4  # comment",
        "fprime_tools==4.4.0",
        'fprime.fpp==3.4.0; sys_platform == "linux"',
        "",
        "# a comment line",
        "pybind11>=2.13",
    ]
    assert divergences(variant, FRAMEWORK) == []
