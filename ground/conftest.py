"""What the ground's tests share: a packer of F´ telemetry downlinks."""

from collections.abc import Sequence
from typing import Any

import numpy as np

from fsw.codegen.dictionary import Dictionary

NS = 1_000_000_000
"""ns per s."""

Write = tuple[str, int, Any]
"""A telemetry write: `<instance>.<channel>`, its time tag in ns and its value."""


class TlmPacker:
    """Packs telemetry writes into the bytes a deployment downlinks, typed by a dictionary.

    Attributes:
        dictionary: the dictionary that types the packets' fields and their channels.
    """

    dictionary: Dictionary

    def __init__(self, dictionary: Dictionary) -> None:
        """Holds the dictionary.

        Args:
            dictionary: the dictionary that types the packets' fields and their channels.
        """
        self.dictionary = dictionary

    def packet(self, writes: Sequence[Write], descriptor: str | int = "FW_PACKET_TELEM") -> bytes:
        """An F´ `TlmPacket`, as the deployment's ground link downlinks it.

        Args:
            writes: each entry's channel name, time tag in ns (a whole number of microseconds) and value.
            descriptor: the `ComCfg.Apid` constant the packet's descriptor holds, or its number.

        Returns:
            A big-endian descriptor, then each entry's channel ID, `Fw.TimeValue` (time base,
            context, seconds, microseconds) and value bytes.
        """
        constants = self.dictionary.type("ComCfg.Apid").constants
        assert constants is not None, "`ComCfg.Apid` is an enum"
        number = constants[descriptor] if isinstance(descriptor, str) else descriptor
        packet = np.array(number, self.dictionary.type("FwPacketDescriptorType").dtype).tobytes()
        for name, t_ns, value in writes:
            channel = self.dictionary.channel(name)
            seconds, remainder = divmod(t_ns, NS)
            packet += np.array(channel.id, self.dictionary.type("FwChanIdType").dtype).tobytes()
            packet += np.array(0, self.dictionary.type("FwTimeBaseStoreType").dtype).tobytes()
            packet += np.array(0, self.dictionary.type("FwTimeContextStoreType").dtype).tobytes()
            packet += np.array([seconds, remainder // 1000], ">u4").tobytes()
            packet += np.asarray(value, dtype=channel.type.dtype.base).tobytes()
        return packet

    def downlink(self, packets: Sequence[bytes]) -> tuple[bytes, bytes]:
        """What `FprimeStation.telemetry` gives for these packets, the one place its form is built.

        Args:
            packets: each packet's bytes, oldest first.

        Returns:
            The packets back to back, and each packet's size as native U32.
        """
        return b"".join(packets), np.array([len(packet) for packet in packets], np.uint32).tobytes()

    def with_channel_id(self, packet: bytes, channel_id: int) -> bytes:
        """A packet of one entry with that entry's channel ID replaced.

        Args:
            packet: a packet of one entry.
            channel_id: the ID to hold.

        Returns:
            The packet, the same size.
        """
        head = len(self.packet([]))
        id_type = self.dictionary.type("FwChanIdType")
        return packet[:head] + np.array(channel_id, id_type.dtype).tobytes() + packet[head + id_type.dtype.itemsize :]
