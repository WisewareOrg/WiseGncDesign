"""The F´ ground station: the F´ build's radio edge, the only F´ packet codec in the repository.

It does a ground data system's job against the deployment's pins: commands go up as F´'s command
packets, responses come down as `Fw.CmdResponse` names, and telemetry comes down as F´'s telemetry
packets, which `decode` turns into values in one batch per channel.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Any

import numpy as np

from fsw.codegen.dictionary import Dictionary

__all__ = ["FprimeStation"]

_SECONDS_AND_MICROSECONDS_SIZE = 8
"""Bytes of an `Fw.TimeValue`'s seconds and microseconds, two U32, which end every entry's header."""


class FprimeStation:
    """The ground's radio edge to an F´ deployment, through the deployment's pins.

    Attributes:
        dictionary: the deployment's dictionary.
    """

    dictionary: Dictionary

    def __init__(self, fsw: Any, dictionary: Dictionary) -> None:
        """Holds the deployment's pins and reads the packet's types from its dictionary.

        Args:
            fsw: the pins: anything with the extension's `uplink`, `responses` and `telemetry`,
                such as a copy of the extension or `lab.Adapter`, which also gives `period_s`.
            dictionary: the deployment's dictionary.
        """
        self._fsw = fsw
        self.dictionary = dictionary
        self._descriptor = dictionary.type("FwPacketDescriptorType")
        self._opcode = dictionary.type("FwOpcodeType")
        apids = dictionary.type("ComCfg.Apid").constants
        assert apids is not None, "`ComCfg.Apid` is an enum"
        self._command_descriptor = apids["FW_PACKET_COMMAND"]
        self._responses = {value: name for name, value in dictionary.responses.items()}
        self._apids = apids
        self._telem_descriptor = apids["FW_PACKET_TELEM"]
        channels = sorted(dictionary.channels_by_id.values(), key=lambda c: c.id)
        self._ids = np.array([c.id for c in channels])
        self._sizes = np.array([c.type.dtype.itemsize for c in channels])
        self._id = dictionary.type("FwChanIdType")
        id_size = self._id.dtype.itemsize
        time_base_and_context = sum(
            dictionary.type(t).dtype.itemsize for t in ("FwTimeBaseStoreType", "FwTimeContextStoreType")
        )
        self._entry_header = id_size + time_base_and_context + _SECONDS_AND_MICROSECONDS_SIZE
        self._seconds_at = self._entry_header - _SECONDS_AND_MICROSECONDS_SIZE

    @property
    def period_s(self) -> float:
        """s, the period the deployment ticks at, as its pins give it.

        Returns:
            The pins' `period_s`.
        """
        return self._fsw.period_s

    def encode_command(self, name: str, args: Mapping[str, Any]) -> bytes:
        """A command packet.

        A name the dictionary lacks raises `KeyError`, as `Dictionary.command` does, and so does a
        missing argument.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name.

        Returns:
            The packet, big-endian: a `FwPacketDescriptorType` holding `FW_PACKET_COMMAND`, a
            `FwOpcodeType`, then the arguments in order.

        Raises:
            ValueError: when a parameter is of a type the dictionary does not code, or an argument
                does not fit its type.
        """
        command = self.dictionary.command(name)
        if command.types is None:
            raise ValueError(f"{name} has a parameter type the dictionary module does not code")
        packet = self._descriptor.serialized([self._command_descriptor]).tobytes()
        packet += self._opcode.serialized([command.opcode]).tobytes()
        for param, ftype in zip(command.params, command.types, strict=True):
            packet += ftype.serialized([args[param]]).tobytes()
        return packet

    def uplink(self, name: str, args: Mapping[str, Any], context: int) -> None:
        """Queues a command at the deployment's dispatcher, which runs it at the next tick.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name, in the command's types.
            context: the ground's number for the command, returned with its response.
        """
        self._fsw.uplink(self.encode_command(name, args), context)

    def responses(self) -> list[tuple[int, str, str | None]]:
        """The command responses since the last call, oldest first.

        Returns:
            `(context, response, None)`: the response a name of `Fw.CmdResponse`; F´ gives no
            reason with it.
        """
        return [(context, self._responses[code], None) for context, code in self._fsw.responses()]

    def telemetry(self) -> tuple[bytes, bytes]:
        """The deployment's downlink since the last call, raw.

        Returns:
            The telemetry packets back to back, oldest first, and each packet's size as native U32.
        """
        return self._fsw.telemetry()

    def decode(
        self, downlinks: Sequence[tuple[bytes, bytes]], names: Collection[str] | None = None
    ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Downlinks as each channel's values, every channel decoded in one batch.

        Each packet is an F´ `TlmPacket`: a `FwPacketDescriptorType` holding `FW_PACKET_TELEM`, then
        entries of a `FwChanIdType`, an `Fw.TimeValue` (time base, time context, seconds and microseconds)
        and the value's bytes, whose size the
        channel's type gives. Every entry is kept, in the order downlinked.

        Args:
            downlinks: as `telemetry` gave them, oldest first.
            names: the channels to decode, `<instance>.<channel>`; every channel when `None`.

        Returns:
            For each channel downlinked, `<instance>.<channel>` to its F´ time tags in ns as int64,
            oldest first, and its values, as `Channel.from_raw` gives them.

        Raises:
            ValueError: for bytes that are not `TlmPacket`s: a packet whose descriptor is not
                `FW_PACKET_TELEM`, an entry whose channel ID is not in the dictionary, packet sizes
                that do not sum to the bytes, and a packet cut short. Each message names the packet.
        """
        data = np.frombuffer(b"".join(packets for packets, _ in downlinks), np.uint8)
        sizes = np.concatenate([np.frombuffer(sizes, np.uint32) for _, sizes in downlinks] or [[]]).astype(np.int64)
        if not sizes.size:
            return {}
        if sizes.sum() != data.size:
            raise ValueError(f"a downlink's packet sizes sum to {sizes.sum()} bytes, not its {data.size}")
        ends = np.cumsum(sizes)
        starts = ends - sizes
        head = self._descriptor.dtype.itemsize
        self._refuse_cut_short(sizes < head)
        descriptors = self._read(data, starts, self._descriptor)
        wrong = np.flatnonzero(descriptors != self._telem_descriptor)
        if wrong.size:
            found = int(descriptors[wrong[0]])
            name = next((n for n, value in self._apids.items() if value == found), found)
            raise ValueError(f"downlinked packet {wrong[0]} is {name}, not FW_PACKET_TELEM")
        positions, ids = [], []
        cursors = starts + head
        id_size = self._id.dtype.itemsize
        while True:
            live = cursors < ends
            if not live.any():
                break
            at = cursors[live]
            self._refuse_cut_short(at + id_size > ends[live], live)
            entry_ids = self._read(data, at, self._id)
            known = np.searchsorted(self._ids, entry_ids)
            unknown = (known >= self._ids.size) | (self._ids[np.minimum(known, self._ids.size - 1)] != entry_ids)
            if unknown.any():
                packet = np.flatnonzero(live)[unknown][0]
                raise ValueError(
                    f"downlinked packet {packet} holds channel ID {entry_ids[unknown][0]:#x}, not in the dictionary"
                )
            after = at + self._entry_header + self._sizes[known]
            self._refuse_cut_short(after > ends[live], live)
            positions.append(at)
            ids.append(entry_ids)
            cursors = cursors.copy()
            cursors[live] = after
        position, chan = np.concatenate(positions), np.concatenate(ids)
        if names is not None:
            wanted = np.isin(chan, [self.dictionary.channel(name).id for name in names])
            position, chan = position[wanted], chan[wanted]
        order = np.argsort(position, kind="stable")
        position, chan = position[order], chan[order]
        seconds = _be_u32(data, position + self._seconds_at)
        useconds = _be_u32(data, position + self._seconds_at + 4)
        t_ns = seconds.astype(np.int64) * 1_000_000_000 + useconds.astype(np.int64) * 1_000
        unique, first = np.unique(chan, return_index=True)
        decoded = {}
        for cid in unique[np.argsort(first)].tolist():
            channel = self.dictionary.channels_by_id[cid]
            mine = chan == cid
            size = channel.type.dtype.itemsize
            value_bytes = data[(position[mine] + self._entry_header)[:, None] + np.arange(size)]
            raw = np.frombuffer(np.ascontiguousarray(value_bytes).tobytes(), channel.type.dtype)
            decoded[channel.name] = (t_ns[mine], channel.from_raw(raw))
        return decoded

    @staticmethod
    def _refuse_cut_short(cut: np.ndarray, live: np.ndarray | None = None) -> None:
        """Raises for the first packet an entry or its descriptor overruns.

        Args:
            cut: for each packet, or each of those `live`, whether it is cut short.
            live: which packets `cut` covers; every packet when `None`.

        Raises:
            ValueError: naming the packet.
        """
        if cut.any():
            packets = np.flatnonzero(cut) if live is None else np.flatnonzero(live)[cut]
            raise ValueError(f"downlinked packet {packets[0]} is cut short")

    @staticmethod
    def _read(data: np.ndarray, at: np.ndarray, ftype: Any) -> np.ndarray:
        """The big-endian values of a type at each offset.

        Args:
            data: the bytes.
            at: each value's offset.
            ftype: the dictionary type of the values.

        Returns:
            (N,) of the type's integers.
        """
        size = ftype.dtype.itemsize
        return np.ascontiguousarray(data[at[:, None] + np.arange(size)]).view(f">u{size}").ravel().astype(np.int64)


def _be_u32(data: np.ndarray, at: np.ndarray) -> np.ndarray:
    """The big-endian U32 at each offset.

    Args:
        data: the bytes.
        at: each U32's offset.

    Returns:
        (N,) uint32.
    """
    return np.ascontiguousarray(data[at[:, None] + np.arange(4)]).view(">u4").ravel()
