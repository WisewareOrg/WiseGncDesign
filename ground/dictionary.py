"""An F´ JSON dictionary as the hosts and the ground use it: names and types.

Entries are named `<instance>.<entry>` with the instance's module dropped, so
`ImuDeadReckoning.nav.navState` is `nav.navState`. A type's numpy dtype is big-endian, as F´
serializes it; the bytes themselves are the F´ ground station's, `ground.fprime_station`.
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

from fsw.codegen.deployment import CLONE, framework_files

__all__ = ["Channel", "Command", "Dictionary", "Parameter", "Type"]

_REPOSITORY = Path(__file__).resolve().parents[1]
_INTERFACES = _REPOSITORY / "fsw" / "fpp" / "interfaces"

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
    command = ["git", "-C", str(CLONE), "describe", "--tags", "--exact-match"]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


@dataclass(frozen=True)
class Type:
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


@dataclass(frozen=True)
class Command:
    """One command of an instance.

    Attributes:
        name: `<instance>.<command>`.
        opcode: the command's opcode.
        params: the parameter names, in order.
        types: each parameter's type, in order, or `None` when one is of a type not coded.
        kind: the dictionary's `commandKind`, such as `sync`, or `set` and `save` for the commands
            F´ generates for a parameter.
    """

    name: str
    opcode: int
    params: tuple[str, ...]
    types: tuple[Type, ...] | None
    kind: str


@dataclass(frozen=True)
class Parameter:
    """One parameter of an instance.

    Attributes:
        id: the parameter's ID.
        name: `<instance>.<parameter>`.
    """

    id: int
    name: str


@dataclass(frozen=True)
class Channel:
    """One telemetry channel.

    Attributes:
        id: the channel's ID.
        name: `<instance>.<channel>`.
        units: the units in the channel's FPP `format`, `"{} m"` giving `m`, else `""`.
        type: the channel's type.
    """

    id: int
    name: str
    units: str
    type: Type

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
            raw = self.type.serialized(written)
        except ValueError as error:
            raise ValueError(f"channel {self.name} cannot take its writes: {error}") from error
        return self.from_raw(raw)

    def from_raw(self, raw: np.ndarray) -> np.ndarray:
        """The values of writes held in the channel's dtype, as `pack_many` returns them.

        Args:
            raw: (N, *shape) in the channel's dtype.

        Returns:
            (N, *shape) float64, a bool as 1.0 or 0.0, or (N,) strings for an enum channel.

        Raises:
            ValueError: naming the channel, for an enum value that is no constant.
        """
        ftype = self.type
        if ftype.constants is None:
            return (raw == ftype.bools[1] if ftype.bools else raw).astype(np.float64)
        names = {value: name for name, value in ftype.constants.items()}
        try:
            return np.array([names[value] for value in raw.tolist()], dtype=str)
        except KeyError as error:
            raise ValueError(f"channel {self.name} has no constant {error}") from error


class Dictionary:
    """One deployment's F´ JSON dictionary, its names without their instances' modules.

    Attributes:
        metadata: the dictionary's `metadata` object.
        responses: `Fw.CmdResponse`'s constants by name.
        channels_by_id: every channel by its ID.
        parameters_by_id: every parameter by its ID.
    """

    metadata: Mapping[str, Any]
    responses: Mapping[str, int]
    channels_by_id: Mapping[int, Channel]
    parameters_by_id: Mapping[int, Parameter]

    def __init__(self, path: Path) -> None:
        """Parses the dictionary.

        A command with a parameter of a type the module does not code loads, and is refused only
        when its arguments are typed, so a deployment's framework commands, which take strings, do
        not stop it loading.

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
        self.responses = self.type("Fw.CmdResponse").constants
        self._commands: dict[str, Command] = {}
        for entry in document["commands"]:
            name = entry["name"].split(".", 1)[1]
            params = tuple(p["name"] for p in entry["formalParams"])
            try:
                types = tuple(self.type(p["type"]["name"]) for p in entry["formalParams"])
            except ValueError:
                types = None
            self._commands[name] = Command(
                name, entry["opcode"], params, types, entry["commandKind"]
            )
        self._channels: dict[str, Channel] = {}
        for entry in document["telemetryChannels"]:
            name = entry["name"].split(".", 1)[1]
            units = re.fullmatch(r"\{\}\s*(.*)", entry.get("format", ""))
            try:
                ftype = self.type(entry["type"]["name"])
            except ValueError as error:
                raise ValueError(f"channel {name} has {error}") from error
            self._channels[name] = Channel(entry["id"], name, units[1] if units else "", ftype)
        self.channels_by_id = {c.id: c for c in self._channels.values()}
        self.parameters_by_id = {
            entry["id"]: Parameter(entry["id"], entry["name"].split(".", 1)[1])
            for entry in document["parameters"]
        }

    @classmethod
    def from_component(
        cls, model: Sequence[Path], component: str, *, instance: str
    ) -> "Dictionary":
        """The dictionary of one component instanced alone, generated from FPP with `fpp-to-dict`.

        The deployment, `Py<Component>`, holds the one instance and is written only into the
        temporary directory `fpp-to-dict` runs in, so nothing is written in the tree. The model is
        `fsw/fpp/interfaces/Interfaces.fpp` and `model`, against the F´ framework files in the
        clone under `fsw/fprime/lib`; `fpp-to-dict` follows the `.fppi` includes. A dictionary is
        generated once per process for each content of its inputs, which the key hashes: the
        deployment, the model, every `.fpp` and `.fppi` under `fsw/fpp/interfaces`, every
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
        imports = list(framework_files())
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

        The module prefix, IDs and opcodes are dropped, and each type is replaced by its full
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

    def command(self, name: str) -> Command:
        """One command by its name.

        Args:
            name: `<instance>.<command>`.

        Returns:
            The command.

        Raises:
            KeyError: when the dictionary has no such command.
        """
        if name not in self._commands:
            raise KeyError(f"no command {name!r}; the dictionary has {sorted(self._commands)}")
        return self._commands[name]

    def arguments(self, name: str, args: Mapping[str, Any]) -> dict[str, Any]:
        """A command's arguments held to its parameters' types, as F´'s handler gets them.

        A name the dictionary lacks raises `KeyError`, as `Dictionary.command` does.

        Args:
            name: `<instance>.<command>`.
            args: the arguments by parameter name.

        Returns:
            Each argument by parameter name, in the parameters' order: an F32 as F32 holds it, a
            bool, an enum constant's name, an integer, or an array of the type's shape.

        Raises:
            ValueError: when the arguments are not exactly the parameters, or one does not fit its
                type.
        """
        command = self.command(name)
        if command.types is None:
            raise ValueError(f"{name} has a parameter type the dictionary module does not code")
        if set(args) != set(command.params):
            raise ValueError(f"{name} takes {list(command.params)}, not {sorted(args)}")
        typed = {}
        for param, ftype in zip(command.params, command.types, strict=True):
            try:
                raw = ftype.serialized([args[param]])[0]
            except ValueError as error:
                raise ValueError(f"{name} parameter {param} cannot take {args[param]!r}") from error
            value = np.array(raw.tolist()) if ftype.dtype.shape else raw.item()
            if ftype.bools:
                value = value == ftype.bools[1]
            elif ftype.constants is not None:
                value = {v: k for k, v in ftype.constants.items()}[value]
            typed[param] = value
        return typed

    def type(self, name: str) -> Type:
        """How a type serializes.

        Args:
            name: the type's qualified name.

        Returns:
            Its `Type`.

        Raises:
            ValueError: naming the type, when it is not a primitive, an alias of one, an enum, or
                an array of primitives or of such arrays.
        """
        if name in _PRIMITIVES:
            bools = self._bools if name == "bool" else None
            return Type(name, np.dtype(_PRIMITIVES[name]), None, bools)
        definition = self._definitions.get(name, {"kind": None})
        if definition["kind"] == "alias":
            return self.type(definition["underlyingType"]["name"])
        if definition["kind"] == "enum":
            representation = self.type(definition["representationType"]["name"])
            constants = {c["name"]: c["value"] for c in definition["enumeratedConstants"]}
            return Type(name, representation.dtype, constants, None)
        if definition["kind"] == "array":
            element = self.type(definition["elementType"]["name"])
            if element.constants is None and element.bools is None:
                shape = (definition["size"], *element.dtype.shape)
                return Type(name, np.dtype((element.dtype.base, shape)), None, None)
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
