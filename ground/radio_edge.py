"""The radio edge: the flight software as the ground sees it, in F´'s names and values."""

from collections.abc import Mapping
from typing import Any, Protocol

import numpy as np

from fsw.codegen.dictionary import Dictionary

__all__ = ["RadioEdge"]


class RadioEdge(Protocol):
    """A flight software build as the ground sees it.

    Commands go up and telemetry comes down by `<instance>.<entry>` name, with values in the
    dictionary's types, and responses by their `Fw.CmdResponse` name, on either build.

    Attributes:
        dictionary: the dictionary the build is held to.
    """

    dictionary: Dictionary

    @property
    def period_s(self) -> float:
        """s, the period the build's flight software ticks at.

        Returns:
            The period.
        """
        ...

    def uplink(self, name: str, args: Mapping[str, Any], context: int) -> None:
        """Queues a command, which runs at the build's next tick.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name, as `Dictionary.arguments` types them.
            context: the ground's number for the command, returned with its response.
        """
        ...

    def responses(self) -> list[tuple[int, str, str | None]]:
        """The command responses since the last call, oldest first.

        Returns:
            `(context, response, reason)`: the response a name of `Fw.CmdResponse`, and why the
            flight software refused the command, when it said, else `None`.
        """
        ...

    def telemetry(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Every telemetry value downlinked since the last call, each channel in one batch.

        Returns:
            For each channel downlinked, `<instance>.<channel>` to its flight software time tags in
            ns, oldest first, and its values, as `Channel.from_raw` gives them.
        """
        ...
