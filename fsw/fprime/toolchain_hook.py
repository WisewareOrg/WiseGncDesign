"""Hatch metadata hook: the framework's own pins for the tools the build and the ground run."""

from pathlib import Path

from hatchling.metadata.plugin.interface import MetadataHookInterface
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

TOOLS = ("cmake", "ninja", "fprime-tools", "fprime-fpp", "fprime-gds")
"""The tools whose version the F´ framework clone fixes."""


class ToolchainHook(MetadataHookInterface):
    """Declares the framework clone's pins of `TOOLS` as the project's dependencies."""

    def update(self, metadata: dict) -> None:
        """Set `dependencies` to the lines of the clone's `requirements.txt` that pin `TOOLS`.

        Args:
            metadata: The project metadata hatchling is building; `dependencies` is set on it.

        Raises:
            ValueError: The clone's `requirements.txt` is absent, a tool in `TOOLS` has no line in
                it, or a tool's line is not a single `==` pin.
        """
        path = Path(self.root) / "lib/fprime/requirements.txt"
        if not path.is_file():
            raise ValueError(f"{path} is absent: run `just _sync` to clone F´")
        pins = {}
        for line in path.read_text().splitlines():
            text = line.split("#", 1)[0].strip()
            if text:
                requirement = Requirement(text)
                pins[canonicalize_name(requirement.name)] = requirement
        missing = [tool for tool in TOOLS if tool not in pins]
        if missing:
            raise ValueError(f"the F´ requirements.txt does not pin {', '.join(missing)}")
        loose = [
            tool for tool in TOOLS if [spec.operator for spec in pins[tool].specifier] != ["=="]
        ]
        if loose:
            raise ValueError(f"the F´ requirements.txt does not pin {', '.join(loose)} with ==")
        metadata["dependencies"] = [str(pins[tool]) for tool in TOOLS]
