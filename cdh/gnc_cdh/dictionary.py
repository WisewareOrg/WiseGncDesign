"""An F´ JSON dictionary as the hosts and the ground use it: names, types and the wire format.

F´ serializes big-endian. A command packet is a `FwPacketDescriptorType` holding
`FW_PACKET_COMMAND`, a `FwOpcodeType`, and the arguments in order. A telemetry value is the
channel's type serialized. Entries are named `<instance>.<entry>` with the deployment prefix
dropped, so `WiseFsw.nav.navState` is `nav.navState`.
"""

import functools
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["Channel", "Command", "DecodeError", "Dictionary"]

_REPOSITORY = Path(__file__).resolve().parents[2]
_INTERFACES = _REPOSITORY / "cdh" / "fprime" / "Interfaces"
_CLONE = _REPOSITORY / "cdh" / "fprime" / "lib" / "fprime"
_FRAMEWORK = (
    "Fw/Buffer/Buffer.fpp",
    "Fw/Cmd/Cmd.fpp",
    "Fw/Dp/Dp.fpp",
    "Fw/Log/Log.fpp",
    "Fw/Time/Time.fpp",
    "Fw/Tlm/Tlm.fpp",
    "Fw/Types/Types.fpp",
    "Svc/Ccsds/Types/Types.fpp",
    "Svc/DpCompressProc/Types/CompressionTypes.fpp",
    "Svc/Sched/Sched.fpp",
    "cmake/platform/unix/Platform/PlatformTypes.fpp",
    "default/config/ComCfg.fpp",
    "default/config/DpCfg.fpp",
    "default/config/FpConfig.fpp",
    "default/config/FpConstants.fpp",
    "default/config/FpySequencerCfg.fpp",
    "default/config/WasmSequencerCfg.fpp",
)
"""The F´ framework files, in the clone, that a component's model imports."""

_PRIMITIVES = {
    "F32": ">f4",
    "F64": ">f8",
    "I8": "i1",
    "I16": ">i2",
    "I32": ">i4",
    "I64": ">i8",
    "U8": "u1",
    "U16": ">u2",
    "U32": ">u4",
    "U64": ">u8",
    "bool": "u1",
}
"""Each primitive F´ type to its big-endian numpy dtype; a bool is one byte,
`FW_SERIALIZE_TRUE_VALUE` or `FW_SERIALIZE_FALSE_VALUE`."""

_generated: dict[str, "Dictionary"] = {}
"""The dictionaries `from_component` generated in this process, by the hash of their inputs."""


@functools.cache
def _tag() -> str:
    """The F´ release the framework clone is at.

    Returns:
        Its tag, such as `v4.4.2`.
    """
    command = ["git", "-C", str(_CLONE), "describe", "--tags", "--exact-match"]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


@dataclass(frozen=True)
class _Type:
    """How a dictionary type serializes.

    A primitive, an enum, or an array of primitives or of such arrays.

    Attributes:
        name: the type's qualified name.
        dtype: its big-endian numpy dtype, an array's shape in it.
        constants: an enum's constants by name, else `None`.
        bools: `(FW_SERIALIZE_FALSE_VALUE, FW_SERIALIZE_TRUE_VALUE)` for a bool, else `None`.
    """

    name: str
    dtype: np.dtype
    constants: Mapping[str, int] | None
    bools: tuple[int, int] | None

    def serialized(self, values: Sequence[Any]) -> np.ndarray:
        """Values as written in Python, held to the type and in its dtype, as F´ would pack them.

        Args:
            values: numbers of the type's kind (an integer for an integer type) and shape, bools,
                or an enum's constant names.

        Returns:
            (N, *shape) in the type's element dtype, whose bytes are the values serialized.

        Raises:
            ValueError: a value is not of the type's kind or shape, is an integer outside its range,
                or names no constant.
        """
        if not len(values):
            return np.empty((0, *self.dtype.shape), self.dtype.base)
        if self.constants is not None:
            try:
                return np.array([self.constants[value] for value in values], self.dtype)
            except (KeyError, TypeError) as error:
                raise ValueError(f"{error!r} is not a constant of {self.name}") from error
        raw = np.array(values)
        kinds = "b" if self.bools else "iuf" if self.dtype.base.kind == "f" else "iu"
        if raw.dtype.kind not in kinds or raw.shape != (len(values), *self.dtype.shape):
            raise ValueError(f"{raw.dtype} of shape {raw.shape[1:]} is not a {self.name}")
        if raw.dtype.kind in "iu" and self.dtype.base.kind in "iu":
            limits = np.iinfo(self.dtype.base)
            if raw.min() < limits.min or raw.max() > limits.max:
                raise ValueError(f"{raw.min()} to {raw.max()} is outside {self.name}")
        if self.bools:
            return np.where(raw, self.bools[1], self.bools[0]).astype(self.dtype)
        return raw.astype(self.dtype.base)


class DecodeError(ValueError):
    """A command packet the dictionary cannot decode, with the `Fw::CmdResponse` it earns.

    Attributes:
        response: the constant's name in `Dictionary.responses`.
    """

    response: str

    def __init__(self, response: str, message: str) -> None:
        """Holds the response and the message.

        Args:
            response: a name in `Dictionary.responses`.
            message: what was wrong.
        """
        super().__init__(message)
        self.response = response


@dataclass(frozen=True)
class Command:
    """One command of an instance.

    Attributes:
        name: `<instance>.<command>`.
        opcode: the command's opcode.
        params: the parameter names, in order.
    """

    name: str
    opcode: int
    params: tuple[str, ...]
    _types: tuple[_Type, ...] | None


@dataclass(frozen=True)
class Channel:
    """One telemetry channel.

    Attributes:
        id: the channel's ID.
        name: `<instance>.<channel>`.
        units: the units in the channel's FPP `format`, `"{} m"` giving `m`, else `""`.
    """

    id: int
    name: str
    units: str
    _type: _Type

    def decode(self, serialized: bytes) -> Any:
        """One write's value, as `decode_many` gives it.

        Args:
            serialized: the value as F´ serializes it.

        Returns:
            The value.
        """
        return self.decode_many([serialized])[0]

    def decode_many(self, serialized: Sequence[bytes]) -> np.ndarray:
        """Every write's value in one array, from the values as F´ serialized them.

        Args:
            serialized: each write's bytes.

        Returns:
            As `pack_many` gives it.

        Raises:
            ValueError: naming the channel, for a write that is not bytes of one value of its type,
                or an enum value that is no constant.
        """
        size = self._type.dtype.itemsize
        if not all(isinstance(value, bytes) and len(value) == size for value in serialized):
            raise ValueError(f"channel {self.name} decodes {size}-byte writes only")
        return self._values(np.frombuffer(b"".join(serialized), self._type.dtype))

    def pack_many(self, written: Sequence[Any]) -> np.ndarray:
        """Every write's value in one array, from the values a Python algorithm wrote.

        Each value is packed into the channel's type as F´ would serialize it: a float type
        truncates, and a value of another kind or shape, an integer outside the type's range, or
        an enum name that is no constant fails.

        Args:
            written: each write's value.

        Returns:
            (N, *shape) float64, a bool as 1.0 or 0.0, or (N,) strings for an enum channel.

        Raises:
            ValueError: naming the channel, when a value does not fit its type.
        """
        try:
            raw = self._type.serialized(written)
        except ValueError as error:
            raise ValueError(f"channel {self.name} cannot take its writes: {error}") from error
        return self._values(raw)

    def _values(self, raw: np.ndarray) -> np.ndarray:
        """The values of serialized writes, as `pack_many` returns them.

        Args:
            raw: (N, *shape) in the channel's dtype.

        Returns:
            (N, *shape) float64, a bool as 1.0 or 0.0, or (N,) strings for an enum channel.

        Raises:
            ValueError: naming the channel, for an enum value that is no constant.
        """
        ftype = self._type
        if ftype.constants is None:
            return (raw == ftype.bools[1] if ftype.bools else raw).astype(np.float64)
        names = {value: name for name, value in ftype.constants.items()}
        try:
            return np.array([names[value] for value in raw.tolist()], dtype=str)
        except KeyError as error:
            raise ValueError(f"channel {self.name} has no constant {error}") from error


class Dictionary:
    """One deployment's F´ JSON dictionary, its names without the deployment prefix.

    Attributes:
        metadata: the dictionary's `metadata` object.
        responses: `Fw.CmdResponse`'s constants by name.
        channels_by_id: every channel by its ID.
    """

    metadata: Mapping[str, Any]
    responses: Mapping[str, int]
    channels_by_id: Mapping[int, Channel]

    def __init__(self, path: Path) -> None:
        """Parses the dictionary.

        A command with a parameter of a type the module does not code loads, and is refused only
        when encoded or decoded, so a deployment's framework commands, which take strings, do not
        stop it loading.

        Args:
            path: the JSON file F´ generated.

        Raises:
            ValueError: naming a channel whose type is not a primitive, an enum, or an array of
                primitives or of such arrays.
        """
        document = json.loads(Path(path).read_text())
        self.metadata = document["metadata"]
        self._document = document
        self._definitions = {t["qualifiedName"]: t for t in document["typeDefinitions"]}
        constants = {c["qualifiedName"]: c["value"] for c in document["constants"]}
        self._bools = (constants["FW_SERIALIZE_FALSE_VALUE"], constants["FW_SERIALIZE_TRUE_VALUE"])
        self._descriptor = self._type("FwPacketDescriptorType")
        self._opcode = self._type("FwOpcodeType")
        self._command_descriptor = self._type("ComCfg.Apid").constants["FW_PACKET_COMMAND"]
        self.responses = self._type("Fw.CmdResponse").constants
        self._commands: dict[str, Command] = {}
        for entry in document["commands"]:
            name = entry["name"].split(".", 1)[1]
            params = tuple(p["name"] for p in entry["formalParams"])
            try:
                types = tuple(self._type(p["type"]["name"]) for p in entry["formalParams"])
            except ValueError:
                types = None
            self._commands[name] = Command(name, entry["opcode"], params, types)
        self._by_opcode = {c.opcode: c for c in self._commands.values()}
        self._channels: dict[str, Channel] = {}
        for entry in document["telemetryChannels"]:
            name = entry["name"].split(".", 1)[1]
            units = re.fullmatch(r"\{\}\s*(.*)", entry.get("format", ""))
            try:
                ftype = self._type(entry["type"]["name"])
            except ValueError as error:
                raise ValueError(f"channel {name} has {error}") from error
            self._channels[name] = Channel(entry["id"], name, units[1] if units else "", ftype)
        self.channels_by_id = {c.id: c for c in self._channels.values()}

    @classmethod
    def from_component(
        cls, model: Sequence[Path], component: str, *, instance: str
    ) -> "Dictionary":
        """The dictionary of one component instanced alone, generated from FPP with `fpp-to-dict`.

        The deployment, `Py<Component>`, holds the one instance and is written only into the
        temporary directory `fpp-to-dict` runs in, so nothing is written in the tree. The model is
        `cdh/fprime/Interfaces/Interfaces.fpp` and `model`, against the F´ framework files in the
        clone under `cdh/fprime/lib`; `fpp-to-dict` follows the `.fppi` includes. A dictionary is
        generated once per process for each content of its inputs, which the key hashes: the
        deployment, the model, every `.fpp` and `.fppi` under `cdh/fprime/Interfaces`, every
        `.fppi` beside a file of `model`, the framework files and the clone's tag.
        A generated dictionary with a channel of a type not coded fails its load with the
        `ValueError` `Dictionary` raises.

        Args:
            model: the component's `.fpp` files.
            component: the component's qualified FPP name, such as `Gnc.ImuDeadReckoner`.
            instance: the instance name, such as `nav`, which prefixes the dictionary's entries.

        Returns:
            The dictionary.

        Raises:
            RuntimeError: `fpp-to-dict` rejected the model, with its stderr.
        """
        name = f"Py{component.rsplit('.', 1)[-1]}"
        deployment = (
            f"module {name} {{\n"
            f"  instance {instance}: {component} base id 0x1000\n"
            f"  deployment topology {name} {{\n    instance {instance}\n  }}\n}}\n"
        )
        sources = [Path(p).resolve() for p in model]
        files = [_INTERFACES / "Interfaces.fpp", *sources]
        imports = [_CLONE / path for path in _FRAMEWORK]
        hashed = [*sources, *sorted(_INTERFACES.rglob("*.fpp*")), *imports]
        hashed += sorted({f for p in sources for f in p.parent.glob("*.fppi")})
        tag = _tag()
        digest = hashlib.sha256(tag.encode() + b"\0" + deployment.encode())
        for path in hashed:
            digest.update(b"\0" + path.read_bytes())
        key = digest.hexdigest()
        if key not in _generated:
            tool = Path(sys.executable).parent / "fpp-to-dict"
            with tempfile.TemporaryDirectory() as out:
                written = Path(out) / "deployment.fpp"
                written.write_text(deployment)
                command = [str(tool), "-d", out, "-f", tag, "-i", ",".join(map(str, imports))]
                command += [*map(str, files), str(written)]
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError(f"fpp-to-dict rejected {component}:\n{result.stderr}")
                _generated[key] = cls(Path(out) / f"{name}TopologyDictionary.json")
        return _generated[key]

    def entries(self, instance: str) -> dict[str, Any]:
        """An instance's commands and channels as the contract states them.

        The deployment prefix, IDs and opcodes are dropped, and each type is replaced by its full
        definition without annotations, so two dictionaries compare equal when the contract is.

        Args:
            instance: the instance name, such as `nav`.

        Returns:
            `commands`: name to its `[parameter name, type]` pairs; `channels`: name to
            `[type, format]`.
        """
        prefix = f"{instance}."
        commands, channels = {}, {}
        for entry in self._document["commands"]:
            name = entry["name"].split(".", 1)[1]
            if name.startswith(prefix):
                params = [[p["name"], self._resolved(p["type"])] for p in entry["formalParams"]]
                commands[name.removeprefix(prefix)] = params
        for entry in self._document["telemetryChannels"]:
            name = entry["name"].split(".", 1)[1]
            if name.startswith(prefix):
                channels[name.removeprefix(prefix)] = [
                    self._resolved(entry["type"]),
                    entry.get("format"),
                ]
        return {"commands": commands, "channels": channels}

    def channel(self, name: str) -> Channel:
        """One channel by its name.

        Args:
            name: `<instance>.<channel>`.

        Returns:
            The channel.

        Raises:
            KeyError: when the dictionary has no such channel.
        """
        if name not in self._channels:
            raise KeyError(f"no channel {name!r}; the dictionary has {sorted(self._channels)}")
        return self._channels[name]

    def encode_command(self, name: str, args: Mapping[str, Any]) -> bytes:
        """A command packet.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name.

        Returns:
            The packet: descriptor, opcode, then the arguments.

        Raises:
            KeyError: when the dictionary has no such command.
            ValueError: when the arguments are not exactly the parameters, or one does not pack.
        """
        if name not in self._commands:
            raise KeyError(f"no command {name!r}; the dictionary has {sorted(self._commands)}")
        command = self._commands[name]
        if command._types is None:
            raise ValueError(f"{name} has a parameter type the dictionary module does not code")
        if set(args) != set(command.params):
            raise ValueError(f"{name} takes {list(command.params)}, not {sorted(args)}")
        packet = self._descriptor.serialized([self._command_descriptor]).tobytes()
        packet += self._opcode.serialized([command.opcode]).tobytes()
        for param, ftype in zip(command.params, command._types, strict=True):
            try:
                packet += ftype.serialized([args[param]]).tobytes()
            except ValueError as error:
                raise ValueError(f"{name} parameter {param} cannot take {args[param]!r}") from error
        return packet

    def decode_command(self, packet: bytes, instance: str) -> tuple[str, dict[str, Any]]:
        """A command packet's command and arguments, as F´'s dispatcher and autocoder decode them.

        Args:
            packet: the bytes.
            instance: the instance the packet is dispatched to.

        Returns:
            The command name without the instance, and its arguments by parameter name: a
            number, a bool, an enum constant's name, or an array.

        Raises:
            DecodeError: `VALIDATION_ERROR` for a packet that is not a command packet,
                `INVALID_OPCODE` for an opcode the instance does not have, and `FORMAT_ERROR` for
                arguments that do not deserialize or do not fill the packet exactly.
        """
        head = self._descriptor.dtype.itemsize + self._opcode.dtype.itemsize
        if len(packet) < head:
            raise DecodeError("VALIDATION_ERROR", f"a packet of {len(packet)} bytes")
        descriptor = np.frombuffer(packet, self._descriptor.dtype, 1)[0]
        opcode = np.frombuffer(packet, self._opcode.dtype, 1, self._descriptor.dtype.itemsize)[0]
        if descriptor != self._command_descriptor:
            raise DecodeError("VALIDATION_ERROR", f"descriptor {descriptor} is not a command")
        command = self._by_opcode.get(int(opcode))
        prefix = f"{instance}."
        if command is None or not command.name.startswith(prefix):
            raise DecodeError("INVALID_OPCODE", f"opcode {opcode} is not {instance}'s")
        if command._types is None:
            raise DecodeError("FORMAT_ERROR", f"{command.name} has a parameter type not coded")
        sizes = [ftype.dtype.itemsize for ftype in command._types]
        if len(packet) != head + sum(sizes):
            raise DecodeError("FORMAT_ERROR", f"{command.name} takes {sum(sizes)} bytes")
        args, at = {}, head
        for param, ftype, size in zip(command.params, command._types, sizes, strict=True):
            raw = np.frombuffer(packet, ftype.dtype, 1, at)[0]
            at += size
            args[param] = self._argument(command, param, ftype, raw)
        return command.name.removeprefix(prefix), args

    def _argument(self, command: Command, param: str, ftype: _Type, raw: np.ndarray) -> Any:
        """One deserialized argument as F´'s autocoder hands it to a handler.

        Args:
            command: the command, for the error.
            param: the parameter, for the error.
            ftype: the parameter's type.
            raw: the argument as deserialized, a numpy scalar or array.

        Returns:
            A number, a bool, an enum constant's name, or an array of the type's shape.

        Raises:
            DecodeError: `FORMAT_ERROR` for a bool byte that is neither of F´'s, or an enum value
                that is no constant.
        """
        value = np.array(raw.tolist()) if ftype.dtype.shape else raw.item()
        if ftype.bools:
            if value not in ftype.bools:
                raise DecodeError("FORMAT_ERROR", f"{command.name} {param}: bool byte {value}")
            return value == ftype.bools[1]
        if ftype.constants is not None:
            names = {v: k for k, v in ftype.constants.items()}
            if value not in names:
                raise DecodeError("FORMAT_ERROR", f"{command.name} {param}: no constant {value}")
            return names[value]
        return value

    def _type(self, name: str) -> _Type:
        """How a type serializes.

        Args:
            name: the type's qualified name.

        Returns:
            Its `_Type`.

        Raises:
            ValueError: naming the type, when it is not a primitive, an alias of one, an enum, or
                an array of primitives or of such arrays.
        """
        if name in _PRIMITIVES:
            bools = self._bools if name == "bool" else None
            return _Type(name, np.dtype(_PRIMITIVES[name]), None, bools)
        definition = self._definitions.get(name, {"kind": None})
        if definition["kind"] == "alias":
            return self._type(definition["underlyingType"]["name"])
        if definition["kind"] == "enum":
            representation = self._type(definition["representationType"]["name"])
            constants = {c["name"]: c["value"] for c in definition["enumeratedConstants"]}
            return _Type(name, representation.dtype, constants, None)
        if definition["kind"] == "array":
            element = self._type(definition["elementType"]["name"])
            if element.constants is None and element.bools is None:
                shape = (definition["size"], *element.dtype.shape)
                return _Type(name, np.dtype((element.dtype.base, shape)), None, None)
        raise ValueError(f"type {name}, which is not coded")

    def _resolved(self, type_json: Mapping[str, Any]) -> Any:
        """A type's name, or its definition without annotations, the types it names resolved alike.

        Args:
            type_json: a `type` object of the dictionary.

        Returns:
            The name of a primitive, or the definition.
        """
        definition = self._definitions.get(type_json["name"])
        if definition is None:
            return type_json["name"]
        shown = {k: v for k, v in definition.items() if k != "annotation"}
        for field in ("elementType", "type", "underlyingType"):
            if field in shown:
                shown[field] = self._resolved(shown[field])
        return shown
