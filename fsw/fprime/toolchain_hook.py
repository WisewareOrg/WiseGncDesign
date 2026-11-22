"""Hatch metadata hook: the framework's own pins for the tools the build and the ground run."""

from pathlib import Path
from urllib.request import urlopen

from hatchling.metadata.plugin.interface import MetadataHookInterface
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

TOOLS = ("cmake", "ninja", "fprime-tools", "fprime-fpp", "fprime-gds")
"""The tools whose version the F´ framework release fixes."""


def toolchain(requirements: str) -> list[str]:
    """Pick the lines of an F´ `requirements.txt` that pin `TOOLS`.

    Args:
        requirements: The text of the release's `requirements.txt`.

    Returns:
        One PEP 508 requirement per tool in `TOOLS`, in that order.

    Raises:
        ValueError: A tool in `TOOLS` has no line, or a tool's line is not a single `==` pin. Any
            other line that is not a PEP 508 requirement raises `packaging`'s
            `InvalidRequirement`, a `ValueError`.
    """
    pins = {}
    for line in requirements.splitlines():
        text = line.split("#", 1)[0].strip()
        if text:
            requirement = Requirement(text)
            pins[canonicalize_name(requirement.name)] = requirement
    missing = [tool for tool in TOOLS if tool not in pins]
    if missing:
        raise ValueError(f"the F´ requirements.txt does not pin {', '.join(missing)}")
    loose = [tool for tool in TOOLS if [spec.operator for spec in pins[tool].specifier] != ["=="]]
    if loose:
        raise ValueError(f"the F´ requirements.txt does not pin {', '.join(loose)} with ==")
    return [str(pins[tool]) for tool in TOOLS]


class ToolchainHook(MetadataHookInterface):
    """Declares the pinned F´ release's pins of `TOOLS` as the project's dependencies."""

    def update(self, metadata: dict) -> None:
        """Set `dependencies` to `toolchain` of the `requirements.txt` at the tag in `fprime-tag`.

        Args:
            metadata: The project metadata hatchling is building; `dependencies` is set on it.

        Raises:
            ValueError: The file cannot be fetched, or `toolchain` refuses it.
        """
        tag = (Path(self.root) / "fprime-tag").read_text().strip()
        url = f"https://raw.githubusercontent.com/nasa/fprime/{tag}/requirements.txt"
        try:
            with urlopen(url, timeout=30) as response:
                requirements = response.read().decode()
        except OSError as error:
            raise ValueError(f"cannot fetch {url}: {error}") from error
        metadata["dependencies"] = toolchain(requirements)
