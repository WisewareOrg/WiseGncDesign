"""Hatch metadata hook: the framework's own pins for the tools the build and the ground run."""

from pathlib import Path

from hatchling.metadata.plugin.interface import MetadataHookInterface

TOOLS = ("cmake", "ninja", "fprime-tools", "fprime-fpp", "fprime-gds")
"""The tools whose version the F´ framework clone fixes; versions are read, never restated."""


class ToolchainHook(MetadataHookInterface):
    """Declares the framework clone's pins of `TOOLS` as the project's dependencies."""

    def update(self, metadata: dict) -> None:
        """Set `dependencies` to the lines of the clone's `requirements.txt` that pin `TOOLS`.

        Args:
            metadata: The project metadata hatchling is building; `dependencies` is set on it.

        Raises:
            ValueError: A tool in `TOOLS` has no line in the clone's `requirements.txt`.
        """
        lines = (Path(self.root) / "lib/fprime/requirements.txt").read_text().splitlines()
        pins = {line.split("==")[0].strip().lower(): line.strip() for line in lines}
        missing = [tool for tool in TOOLS if tool not in pins]
        if missing:
            raise ValueError(f"the F´ requirements.txt does not pin {', '.join(missing)}")
        metadata["dependencies"] = [pins[tool] for tool in TOOLS]
