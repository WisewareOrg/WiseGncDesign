"""The radio edge: the flight software as the ground sees it, in F´'s names and values."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import numpy as np

from ground.dictionary import Dictionary

__all__ = ["RadioEdge"]


class RadioEdge(Protocol):
    """A flight software build as the ground sees it.

    Commands go up and telemetry comes down by `<instance>.<entry>` name, with values in the
    dictionary's types, and responses by their `Fw.CmdResponse` name, on either build.

    Attributes:
        period_s: s, the period the build's flight software ticks at.
        dictionary: the dictionary the build is held to.
    """

    period_s: float
    dictionary: Dictionary

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

    def telemetry(self) -> list[tuple[str, int, Any]]:
        """Every telemetry write since the last call, in the order written.

        Returns:
            `(<instance>.<channel>, time tag in ns, raw)`, the raw write in the build's own form.
        """
        ...

    def values(self, name: str, raws: Sequence[Any]) -> np.ndarray:
        """One channel's raw writes as values, in one batch.

        Args:
            name: `<instance>.<channel>`.
            raws: its raw writes, as `telemetry` gave them.

        Returns:
            As `Channel.from_raw` gives them.
        """
        ...
