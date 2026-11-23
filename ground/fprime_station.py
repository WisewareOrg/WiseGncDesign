"""The F´ ground station: the F´ build's radio edge, the only F´ packet codec in the repository.

It does a ground data system's job against the deployment's pins: commands go up as F´'s command
packets, responses come down as `Fw.CmdResponse` names, and each telemetry write comes down as the
bytes F´ serialized, which `values` turns into values in one batch.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Any

import numpy as np

from fsw.codegen.dictionary import Dictionary

__all__ = ["FprimeStation"]


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
        self._telem_descriptor = apids["FW_PACKET_TELEM"]
        channels = sorted(dictionary.channels_by_id.values(), key=lambda c: c.id)
        self._ids = np.array([c.id for c in channels])
        self._sizes = np.array([c.type.dtype.itemsize for c in channels])
        id_size = dictionary.type("FwChanIdType").dtype.itemsize
        time_size = sum(dictionary.type(t).dtype.itemsize for t in ("FwTimeBaseStoreType", "FwTimeContextStoreType")) + 8
        self._entry_header = id_size + time_size
        self._seconds_at = self._entry_header - 8

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
        entries of a `FwChanIdType`, an `Fw.TimeValue` and the value's bytes, whose size the
        channel's type gives.

        Args:
            downlinks: as `telemetry` gave them, oldest first.
            names: the channels to decode, `<instance>.<channel>`; every channel when `None`.

        Returns:
            For each channel downlinked, `<instance>.<channel>` to its F´ time tags in ns, oldest
            first, and its values, as `Channel.from_raw` gives them.
        """
        data = np.frombuffer(b"".join(packets for packets, _ in downlinks), np.uint8)
        sizes = np.concatenate([np.frombuffer(sizes, np.uint32) for _, sizes in downlinks] or [[]]).astype(np.int64)
        if not sizes.size:
            return {}
        ends = np.cumsum(sizes)
        starts = ends - sizes
        descriptors = (data[starts].astype(np.int64) << 8) | data[starts + 1]
        assert (descriptors == self._telem_descriptor).all(), "a downlinked packet is not FW_PACKET_TELEM"
        positions, ids = [], []
        cursors = starts + self._descriptor.dtype.itemsize
        while True:
            live = cursors < ends
            if not live.any():
                break
            at = cursors[live]
            entry_ids = _be_u32(data, at)
            positions.append(at)
            ids.append(entry_ids)
            cursors = cursors.copy()
            cursors[live] = at + self._entry_header + self._sizes[np.searchsorted(self._ids, entry_ids)]
        position, chan = np.concatenate(positions), np.concatenate(ids)
        if names is not None:
            wanted = np.isin(chan, [self.dictionary.channel(name).id for name in names])
            position, chan = position[wanted], chan[wanted]
        order = np.argsort(position, kind="stable")
        position, chan = position[order], chan[order]
        seconds = _be_u32(data, position + self._seconds_at)
        useconds = _be_u32(data, position + self._seconds_at + 4)
        t_ns = seconds.astype(np.int64) * 1_000_000_000 + useconds.astype(np.int64) * 1_000
        decoded = {}
        for cid in np.unique(chan).tolist():
            channel = self.dictionary.channels_by_id[cid]
            mine = chan == cid
            size = channel.type.dtype.itemsize
            value_bytes = data[(position[mine] + self._entry_header)[:, None] + np.arange(size)]
            raw = np.frombuffer(np.ascontiguousarray(value_bytes).tobytes(), channel.type.dtype)
            decoded[channel.name] = (t_ns[mine], channel.from_raw(raw))
        return decoded


def _be_u32(data: np.ndarray, at: np.ndarray) -> np.ndarray:
    """The big-endian U32 at each offset.

    Args:
        data: the bytes.
        at: each U32's offset.

    Returns:
        (N,) uint32.
    """
    return np.ascontiguousarray(data[at[:, None] + np.arange(4)]).view(">u4").ravel()
