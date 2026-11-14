"""FPP's model, read from the native `fpp to-json`: the one module that reads its output.

The binary is the native one inside the `fprime_fpp` package, run directly. A key the reader needs
that is missing from the output raises `KeyError`. Every name is FPP's qualified name, such as
`ImuDeadReckoning.nav` or `Gnc.Vector3`. A type reference is a primitive's name (`F64`, `U8`,
`bool`), `string`, or a named type's qualified name; an alias reads as the type it names. Why one
module reads `to-json` directly is in ADR 0004 rev 2.
"""

import json
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import fprime_fpp

__all__ = [
    "Argument",
    "Array",
    "Channel",
    "Command",
    "Component",
    "Connection",
    "Enum",
    "Instance",
    "Member",
    "Model",
    "Parameter",
    "Port",
    "Struct",
    "parse",
    "read",
]

_FPP = Path(fprime_fpp.__file__).with_name("fpp")
"""The native `fpp` binary, bypassing the package's wrapper."""

_ANNOTATED = {
    "DefArray",
    "DefComponent",
    "DefComponentInstance",
    "DefConstant",
    "DefEnum",
    "DefStruct",
    "DefTopology",
}
"""The definitions whose annotations are read."""


class Instance(NamedTuple):
    """A component instance.

    Attributes:
        name: its qualified name, such as `ImuDeadReckoning.nav`.
        component: its component's qualified name, such as `Gnc.ImuDeadReckoner`.
        base_id: its base ID.
    """

    name: str
    component: str
    base_id: int


class Connection(NamedTuple):
    """One connection of a topology, with both port numbers resolved.

    Attributes:
        from_instance: the output instance's qualified name.
        from_port: the output port's name.
        from_index: the output port's number.
        to_instance: the input instance's qualified name.
        to_port: the input port's name.
        to_index: the input port's number.
    """

    from_instance: str
    from_port: str
    from_index: int
    to_instance: str
    to_port: str
    to_index: int


class Member(NamedTuple):
    """A struct member.

    Attributes:
        name: the member's name.
        type: its type reference.
        size: its array size, or `None` for a member that is not an array.
    """

    name: str
    type: str
    size: int | None


class Struct(NamedTuple):
    """A struct type.

    Attributes:
        name: its qualified name.
        members: its members, in FPP's order.
    """

    name: str
    members: tuple[Member, ...]


class Enum(NamedTuple):
    """An enum type.

    Attributes:
        name: its qualified name.
        rep_type: its representation type, such as `I32`.
        constants: each constant's value, by name.
    """

    name: str
    rep_type: str
    constants: dict[str, int]


class Array(NamedTuple):
    """An array type.

    Attributes:
        name: its qualified name.
        size: its number of elements.
        element: its element's type reference.
    """

    name: str
    size: int
    element: str


class Argument(NamedTuple):
    """A command argument.

    Attributes:
        name: the argument's name.
        type: its type reference.
    """

    name: str
    type: str


class Command(NamedTuple):
    """A command a component declares.

    Attributes:
        name: the command's name.
        args: its arguments, in order.
    """

    name: str
    args: tuple[Argument, ...]


class Channel(NamedTuple):
    """A telemetry channel a component declares.

    Attributes:
        name: the channel's name.
        type: its type reference.
    """

    name: str
    type: str


class Parameter(NamedTuple):
    """A parameter a component declares.

    Attributes:
        name: the parameter's name.
        type: its type reference.
        default: its FPP default, an enum's as the constant's name, or `None` when FPP gives none.
    """

    name: str
    type: str
    default: int | float | bool | str | None


class Port(NamedTuple):
    """A general output port a component declares.

    Attributes:
        name: the port's name.
        size: its number of ports, 1 for a port that is not an array.
        args: its port type's arguments, in order.
    """

    name: str
    size: int
    args: tuple[Argument, ...]


class Component(NamedTuple):
    """A component's commands, channels, parameters and general output ports, each in FPP's order.

    F´'s implicit parameter set and save commands are not among the commands, and special ports,
    such as `telemetry port`, are not among the outputs. Output ports imported from an interface
    follow the component's own, in the order `to-json` parsed them.

    Attributes:
        name: its qualified name.
        commands: its commands.
        channels: its telemetry channels.
        parameters: its parameters.
        outputs: its general output ports.
        file: the absolute path of the file that defines it.
    """

    name: str
    commands: tuple[Command, ...]
    channels: tuple[Channel, ...]
    parameters: tuple[Parameter, ...]
    outputs: tuple[Port, ...]
    file: Path


class Model(NamedTuple):
    """An FPP model, framework definitions included, by qualified name.

    Attributes:
        instances: every component instance.
        topologies: each topology's connections, an imported topology's among them, sorted by
            `(from_instance, from_port, from_index)`.
        constants: every integer and float constant.
        types: every struct, enum and array type.
        components: every component.
        annotations: each component's, instance's, topology's, constant's and struct, enum or array
            type's `@` lines, then its `@<` lines.
    """

    instances: dict[str, Instance]
    topologies: dict[str, tuple[Connection, ...]]
    constants: dict[str, int | float]
    types: dict[str, Struct | Enum | Array]
    components: dict[str, Component]
    annotations: dict[str, tuple[str, ...]]


class _Node(NamedTuple):
    """A definition in the AST.

    Attributes:
        name: its qualified name.
        kind: its AST kind, such as `DefComponent`.
        data: its AST node's data.
        annotation: its `@` lines, then its `@<` lines.
    """

    name: str
    kind: str
    data: dict[str, Any]
    annotation: tuple[str, ...]


def read(files: Sequence[Path]) -> Model:
    """The model of FPP files, through `fpp to-json` run in a temporary directory.

    Args:
        files: the model's `.fpp` files, the framework's it uses among them; `to-json` follows
            their `.fppi` includes.

    Returns:
        The model.

    Raises:
        RuntimeError: `to-json` rejected the model, with its stderr.
    """
    with tempfile.TemporaryDirectory() as out:
        command = [str(_FPP), "to-json", "-d", out, *map(str, files)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"fpp to-json rejected the model:\n{result.stderr}")
        return parse(Path(out))


def parse(directory: Path) -> Model:
    """The model in `to-json`'s output.

    A key the reader needs that is not in the output raises `KeyError`, and a parameter's default
    that is not a scalar raises `ValueError`, naming the parameter.

    Args:
        directory: where `to-json` wrote `fpp-analysis.json`, `fpp-ast.json` and
            `fpp-loc-map.json`.

    Returns:
        The model.
    """
    analysis = json.loads((directory / "fpp-analysis.json").read_text())["analysis"]
    ast = json.loads((directory / "fpp-ast.json").read_text())["ast"]
    locations = json.loads((directory / "fpp-loc-map.json").read_text())["locationMap"]
    nodes = dict(node for unit in ast for node in _definitions(unit["members"], ()))
    instance_map = analysis["componentInstanceMap"]
    type_map = analysis["typeMap"]
    values = analysis["valueMap"]

    instances = {}
    for entry in instance_map.values():
        qualified = _qualified(entry)
        component = nodes[str(entry["component"]["astNodeId"])].name
        instances[qualified] = Instance(qualified, component, entry["baseId"])

    topologies = {
        _qualified(topology): _connections(topology, instance_map)
        for topology in analysis["topologyMap"].values()
    }

    constants = {}
    types: dict[str, Struct | Enum | Array] = {}
    for node_id, node in nodes.items():
        if node.kind == "DefConstant":
            ((kind, value),) = values[node_id].items()
            if kind in ("Integer", "Float"):
                constants[node.name] = value["value"]
        elif node.kind == "DefStruct":
            types[node.name] = _struct(node, type_map[node_id]["Struct"], nodes)
        elif node.kind == "DefEnum":
            types[node.name] = _enum(node, type_map[node_id]["Enum"], values)
        elif node.kind == "DefArray":
            types[node.name] = _array(node, type_map[node_id]["Array"], nodes)

    components = {}
    for node_id, entry in analysis["componentMap"].items():
        file = Path(locations[node_id]["file"])
        component = _component(nodes[node_id], entry, type_map, nodes, file)
        components[component.name] = component

    annotations = {n.name: n.annotation for n in nodes.values() if n.kind in _ANNOTATED}
    return Model(instances, topologies, constants, types, components, annotations)


def _definitions(members: list[Any], qualifier: tuple[str, ...]) -> Iterator[tuple[str, _Node]]:
    """Every definition among a module's or component's members, and in those nested in them.

    Args:
        members: the members, each `[pre-annotations, {kind: {"node": ...}}, post-annotations]`.
        qualifier: the enclosing modules' and component's names.

    Yields:
        tuple[str, _Node]: each definition's AST node id, as the analysis keys it, and its node.
    """
    for pre, member, post in members:
        ((kind, body),) = member.items()
        if not kind.startswith("Def"):
            continue
        node = body["node"]["AstNode"]
        name = ".".join((*qualifier, node["data"]["name"]))
        yield str(node["id"]), _Node(name, kind, node["data"], (*pre, *post))
        if kind in ("DefModule", "DefComponent"):
            yield from _definitions(node["data"]["members"], (*qualifier, node["data"]["name"]))


def _connections(topology: dict[str, Any], instance_map: dict[str, Any]) -> tuple[Connection, ...]:
    """A topology's connections, each port number resolved.

    Args:
        topology: the topology's analysis entry.
        instance_map: the analysis's component instances, by AST node id.

    Returns:
        Every connection of every group, sorted.
    """
    from_numbers = {_key(c): n for c, n in topology["fromPortNumberMap"]}
    to_numbers = {_key(c): n for c, n in topology["toPortNumberMap"]}

    def end(side: dict[str, Any]) -> tuple[str, str]:
        """One end of a connection.

        Args:
            side: the connection's `from` or `to`.

        Returns:
            The instance's qualified name and the port's name.
        """
        port = side["port"]
        instance = port["interfaceInstance"]["InterfaceComponentInstance"]["astNodeId"]
        ((_, port_instance),) = port["portInstance"].items()
        return _qualified(instance_map[str(instance)]), port_instance["specifier"]["name"]

    connections = []
    for group in topology["connectionMap"].values():
        for c in group:
            from_instance, from_port = end(c["from"])
            to_instance, to_port = end(c["to"])
            from_index, to_index = from_numbers[_key(c)], to_numbers[_key(c)]
            connections.append(
                Connection(from_instance, from_port, from_index, to_instance, to_port, to_index)
            )
    return tuple(sorted(connections, key=lambda c: (c.from_instance, c.from_port, c.from_index)))


def _struct(node: _Node, struct: dict[str, Any], nodes: dict[str, _Node]) -> Struct:
    """A struct type, its members in FPP's order.

    Args:
        node: the struct's definition.
        struct: its type map entry's `Struct`, whose members are in no useful order.
        nodes: every definition, by AST node id.

    Returns:
        The struct.
    """
    members = []
    for _, member, _ in node.data["members"]:
        name = member["AstNode"]["data"]["name"]
        member_type = _type_name(struct["anonStruct"]["members"][name], nodes)
        members.append(Member(name, member_type, struct["sizes"].get(name)))
    return Struct(node.name, tuple(members))


def _enum(node: _Node, enum: dict[str, Any], values: dict[str, Any]) -> Enum:
    """An enum type.

    Args:
        node: the enum's definition.
        enum: its type map entry's `Enum`.
        values: the analysis's values, by AST node id.

    Returns:
        The enum.
    """
    constants = {}
    for _, constant, _ in node.data["constants"]:
        name, number = values[str(constant["AstNode"]["id"])]["EnumConstant"]["value"]
        constants[name] = number
    return Enum(node.name, next(iter(enum["repType"]["kind"])), constants)


def _array(node: _Node, array: dict[str, Any], nodes: dict[str, _Node]) -> Array:
    """An array type.

    Args:
        node: the array's definition.
        array: its type map entry's `Array`.
        nodes: every definition, by AST node id.

    Returns:
        The array.
    """
    anonymous = array["anonArray"]
    return Array(node.name, anonymous["size"]["Some"], _type_name(anonymous["eltType"], nodes))


def _component(
    node: _Node,
    entry: dict[str, Any],
    type_map: dict[str, Any],
    nodes: dict[str, _Node],
    file: Path,
) -> Component:
    """A component's declared commands, channels, parameters and general output ports.

    Args:
        node: the component's definition.
        entry: its analysis entry.
        type_map: the analysis's types, by AST node id.
        nodes: every definition, by AST node id.
        file: the file that defines it.

    Returns:
        The component, each kind of entry in FPP's order.
    """
    specs = {}
    for position, (_, member, _) in enumerate(node.data["members"]):
        ((_, body),) = member.items()
        specs[str(body["node"]["AstNode"]["id"])] = position, body["node"]["AstNode"]["data"]

    def spec(analysis_entry: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """A command's, channel's or parameter's place among the members, and its AST data.

        Args:
            analysis_entry: its analysis entry.

        Returns:
            Its member position and its AST node's data.
        """
        return specs[str(analysis_entry["aNode"]["astNodeId"])]

    def arguments(params: list[Any]) -> tuple[Argument, ...]:
        """A command's or port type's formal parameters, as arguments.

        Args:
            params: the AST's `params`.

        Returns:
            The arguments, in order.
        """
        args = []
        for _, arg, _ in params:
            arg_data = arg["AstNode"]["data"]
            type_node = arg_data["typeName"]["AstNode"]["id"]
            args.append(Argument(arg_data["name"], _type_name(type_map[str(type_node)], nodes)))
        return tuple(args)

    commands = []
    for command in entry["commandMap"].values():
        if "Param" not in command:
            position, data = spec(command["NonParam"])
            commands.append((position, Command(data["name"], arguments(data["params"]))))
    channels = []
    for channel in entry["tlmChannelMap"].values():
        position, data = spec(channel)
        channels.append(
            (position, Channel(data["name"], _type_name(channel["channelType"], nodes)))
        )
    parameters = []
    for parameter in entry["paramMap"].values():
        position, data = spec(parameter)
        default = _default(data["name"], parameter["default"])
        parameter_type = _type_name(parameter["paramType"], nodes)
        parameters.append((position, Parameter(data["name"], parameter_type, default)))
    outputs = []
    for port in entry["portInterface"]["portMap"].values():
        general = port.get("General")
        if general and general["kind"] == "Output":
            node_id = general["aNode"]["astNodeId"]
            position = (0, specs[str(node_id)][0]) if str(node_id) in specs else (1, node_id)
            port_type = nodes[str(general["ty"]["DefPort"]["symbol"]["Port"]["nodeId"])]
            args = arguments(port_type.data["params"])
            outputs.append((position, Port(general["specifier"]["name"], general["size"], args)))
    return Component(
        node.name,
        tuple(c for _, c in sorted(commands)),
        tuple(c for _, c in sorted(channels)),
        tuple(p for _, p in sorted(parameters)),
        tuple(p for _, p in sorted(outputs)),
        file,
    )


def _type_name(t: dict[str, Any], nodes: dict[str, _Node]) -> str:
    """A type, as the analysis writes it, as a type reference.

    Args:
        t: the type.
        nodes: every definition, by AST node id.

    Returns:
        A primitive's name, `string`, or a named type's qualified name; an alias's is the type it
        names.
    """
    ((kind, body),) = t.items()
    if kind == "Primitive":
        ((primitive, detail),) = body.items()
        return "bool" if primitive == "Boolean" else next(iter(detail["kind"]))
    if kind == "Int":
        return next(iter(body["PrimitiveInt"]["kind"]))
    if kind == "String":
        return "string"
    if kind == "AliasType":
        return _type_name(body["aliasType"], nodes)
    return nodes[str(body["node"]["astNodeId"])].name


def _default(parameter: str, default: Any) -> int | float | bool | str | None:
    """A parameter's default as a Python value.

    Args:
        parameter: the parameter's name, for the error.
        default: the analysis's `"None"` or `{"Some": value}`.

    Returns:
        The value, an enum's as its constant's name, or `None` when FPP gives none.

    Raises:
        ValueError: the default is not a scalar.
    """
    if default == "None":
        return None
    ((kind, value),) = default["Some"].items()
    if kind == "EnumConstant":
        return value["value"][0]
    if kind in ("Integer", "PrimitiveInt", "Float", "Boolean", "String"):
        return value["value"]
    raise ValueError(f"parameter {parameter}'s default is a {kind}, not a scalar")


def _qualified(entry: dict[str, Any]) -> str:
    """An analysis entry's qualified name.

    Args:
        entry: an analysis entry with a `qualifiedName`.

    Returns:
        The name, such as `ImuDeadReckoning.nav`.
    """
    name = entry["qualifiedName"]
    return ".".join((*name["qualifier"], name["base"]))


def _key(connection: dict[str, Any]) -> str:
    """A connection as a key, matching the port number maps' connections to the connection map's.

    Args:
        connection: a connection, as the analysis writes it.

    Returns:
        Its canonical JSON.
    """
    return json.dumps(connection, sort_keys=True)
