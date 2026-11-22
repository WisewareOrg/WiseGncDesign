"""The F´ ground station: the F´ build's radio edge, the only F´ packet codec in the repository.

It does a ground data system's job against the deployment's pins: commands go up as F´'s command
packets, responses come down as `Fw.CmdResponse` names, and each telemetry write comes down as the
bytes F´ serialized, which `values` turns into values in one batch.
"""

from collections.abc import Mapping, Sequence
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
        self._command_descriptor = dictionary.type("ComCfg.Apid").constants["FW_PACKET_COMMAND"]
        self._responses = {value: name for name, value in dictionary.responses.items()}

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

    def telemetry(self) -> dict[str, tuple[np.ndarray, bytes]]:
        """Every telemetry write since the last call, by channel.

        Returns:
            For each written channel, `<instance>.<channel>` to its writes' F´ time tags in ns and
            their bytes as F´ serialized them, concatenated, oldest first.
        """
        channels = self.dictionary.channels_by_id
        return {
            channels[i].name: (np.frombuffer(t_ns, np.uint64).astype(np.int64), raw)
            for i, (t_ns, raw) in self._fsw.telemetry().items()
        }

    def values(self, name: str, raws: Sequence[bytes]) -> np.ndarray:
        """One channel's writes as values, in one batch.

        Args:
            name: `<instance>.<channel>`.
            raws: chunks of its writes, as `telemetry` gave them.

        Returns:
            As `Channel.from_raw` gives them.

        Raises:
            ValueError: naming the channel, for bytes that are not whole values of its type.
        """
        channel = self.dictionary.channel(name)
        size = channel.type.dtype.itemsize
        data = b"".join(raws)
        if len(data) % size:
            raise ValueError(f"channel {name} decodes {size}-byte writes only")
        return channel.from_raw(np.frombuffer(data, channel.type.dtype))
