"""The link between the ground and a flight software host, in the form F´ uses."""

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np

from gnc_cdh.dictionary import Channel, Dictionary

__all__ = ["Link"]


class Link(Protocol):
    """A flight software host as the ground sees it.

    Attributes:
        period_s: s, the period the host's flight software ticks at.
        dictionary: the dictionary the build is held to.
        failure: the exception the host's tick raised, kept whole for the harness to re-raise in
            place of the `RuntimeError` Basilisk reports it as, else `None`.
    """

    period_s: float
    dictionary: Dictionary
    failure: BaseException | None

    def uplink(self, packet: bytes, context: int) -> None:
        """Queues a command packet, which runs at the host's next tick.

        Args:
            packet: the serialized command packet.
            context: the ground's number for the command, returned with its response.
        """
        ...

    def responses(self) -> list[tuple[int, int]]:
        """The command responses since the last call, oldest first.

        Returns:
            `(context, response)`, the response a value of the dictionary's `Fw.CmdResponse`.
        """
        ...

    def telemetry(self) -> list[tuple[int, int, Any]]:
        """Every telemetry write since the last call, in the order written.

        Returns:
            `(channel ID, time tag in ns, payload)`, the payload in the host's own form.
        """
        ...

    def values(self, channel: Channel, payloads: Sequence[Any]) -> np.ndarray:
        """The values of one channel's payloads, in one batch.

        Args:
            channel: the channel written.
            payloads: its writes' payloads, as `telemetry` gave them.

        Returns:
            As `Channel.pack_many` and `Channel.decode_many` give them.
        """
        ...
