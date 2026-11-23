"""The GNC partition: a configuration's GNC sub-topology's algorithms, run as its FPP wires them.

The sub-topology is `<configuration>.Gnc`. Its one `Svc.RateGroupDriver` drives its
`Svc.PassiveRateGroup`s, in `CycleOut` order, and each rate group runs its members in
`RateGroupMemberOut` order; every other connection between its instances carries data. An algorithm
is a class named as its member's FPP component, built at `boot` on its parameters. Its `step` takes
`t`, in s, and a keyword per data input, named as the input port without its trailing `In`, and
returns its `<Name>Outputs` and `<Name>Telemetry` tuples, the generated ones, whose fields are read
by position; it must not change a returned output in place, since the member it is routed to holds
it as written. A connection `A.X -> B.Y` routes `A`'s output `X` to `B`'s input `Y`, as an F´ sync
port does: an output reaches a later member in the same frame, and a `None` output writes nothing,
so an input holds the latest value written to it. A backward edge, into a member that runs no later
than `A` in the frame, `A` itself included, is refused, as is an output feeding more than one input.
A sub-topology `port` other than the driver's exposes an instance's port: an input the CDH writes,
or an output the CDH reads, which a frame returns when a member wrote it. An output exposed and
also routed to an input is refused.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

from fsw.codegen.fpp_model import Model
from fsw.codegen.members import DRIVER
from fsw.codegen.members import members as rate_group_members

__all__ = ["Frame", "GncPartition", "MemberTelemetry"]

_RATE_GROUP = "Svc.PassiveRateGroup"
"""The component type of its rate groups."""


def _name(instance: str) -> str:
    """An instance's name with its module dropped, as the dictionary names it.

    Args:
        instance: its qualified name, `<configuration>.<instance>`.

    Returns:
        The name, `<instance>`.
    """
    return instance.split(".", 1)[1]


def _keyword(instance: str, port: str) -> str:
    """The `step` keyword of a data input: the port's name without its trailing `In`.

    Args:
        instance: the instance's qualified name, named when refused.
        port: the input port.

    Returns:
        The keyword.

    Raises:
        ValueError: the port's name does not end in `In`, naming it.
    """
    if not port.endswith("In"):
        raise ValueError(
            f"{_name(instance)}.{port} is a data input whose name does not end in In, so it names no step keyword"
        )
    return port.removesuffix("In")


class MemberTelemetry(NamedTuple):
    """What one member wrote in a frame.

    Attributes:
        instance: its instance's unqualified name.
        telemetry: its `<Name>Telemetry` tuple.
    """

    instance: str
    telemetry: Any


class _Member(NamedTuple):
    """A member as a frame runs it, planned at boot.

    Attributes:
        member: its instance's qualified name.
        name: its instance's unqualified name.
        step: its algorithm's `step`.
        inputs: the inputs it holds, by `step` keyword.
        wanted: how many inputs it takes.
        routed: for each output port routed to a later member, its position in the `<Name>Outputs`
            tuple, that member's inputs and its keyword.
        exposed: for each output port the sub-topology exposes, its position and the port's name.
    """

    member: str
    name: str
    step: Callable[..., tuple[Any, Any]]
    inputs: dict[str, Any]
    wanted: int
    routed: tuple[tuple[int, dict[str, Any], str], ...]
    exposed: tuple[tuple[int, str], ...]


class Frame(NamedTuple):
    """What one frame's members wrote.

    Attributes:
        telemetry: each member's telemetry, in the order run.
        outputs: the value written to each sub-topology output port, by the port; a port no member
            wrote in the frame is absent.
    """

    telemetry: list[MemberTelemetry]
    outputs: dict[str, Any]


class GncPartition:
    """A configuration's GNC sub-topology's algorithms, wired and ordered as its FPP says.

    Attributes:
        rate_groups: each rate group's qualified name, in its driver's `CycleOut` order; a frame's
            rate groups are named by their position here.
        components: each member's FPP component's qualified name, by its instance's name.
        algorithms: each algorithm `boot` built, by its instance's unqualified name.
    """

    rate_groups: tuple[str, ...]
    components: dict[str, str]
    algorithms: dict[str, Any]

    def __init__(self, model: Model, configuration: str, classes: Sequence[type]) -> None:
        """Reads the sub-topology's wiring and matches each member to its class.

        Args:
            model: the model holding the sub-topology `<configuration>.Gnc`.
            configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`.
            classes: the algorithms' classes, one per member's component, each named as it.

        Raises:
            ValueError: the sub-topology has other than one rate group driver; a member's component
                has no class, or a class no member; a data input is not named `<keyword>In`; a data
                connection is a backward edge; or an output feeds more than one input, or both an
                input and a sub-topology port, naming it.
        """
        topology = f"{configuration}.Gnc"
        connections = model.topologies[topology]
        component = {c.from_instance: model.instances[c.from_instance].component for c in connections} | {
            c.to_instance: model.instances[c.to_instance].component for c in connections
        }
        groups = rate_group_members(model, configuration)
        driver = next(i for i, kind in component.items() if kind == DRIVER)
        self.rate_groups = tuple(groups)
        self._members = tuple(tuple(m.name for m in group) for group in groups.values())
        members = {m for group in self._members for m in group}
        by_name = {cls.__name__: cls for cls in classes}
        wanted = {m: model.instances[m].component.rsplit(".", 1)[-1] for m in members}
        missing = sorted(set(wanted.values()) - set(by_name))
        extra = sorted(set(by_name) - set(wanted.values()))
        if missing or extra:
            raise ValueError(f"{topology}: no class for the components {missing}; the classes {extra} match no member")
        self._classes = {m: by_name[name] for m, name in wanted.items()}
        self.components = {_name(m): model.instances[m].component for m in members}

        scheduling = {i for i, kind in component.items() if kind in (DRIVER, _RATE_GROUP)}
        order = {m: n for n, m in enumerate(m for group in self._members for m in group)}
        self._keywords: dict[str, set[str]] = {m: set() for m in members}
        self._routes: dict[tuple[str, str], tuple[str, str]] = {}
        for c in connections:
            if c.from_instance not in scheduling:
                edge = f"{_name(c.from_instance)}.{c.from_port} -> {_name(c.to_instance)}.{c.to_port}"
                if order[c.to_instance] <= order[c.from_instance]:
                    raise ValueError(
                        f"{edge} is a backward edge into a member that runs no later in the"
                        " frame, a one-frame-delayed feedback, which is not supported"
                    )
                if (c.from_instance, c.from_port) in self._routes:
                    raise ValueError(
                        f"{_name(c.from_instance)}.{c.from_port} routes to more than one input,"
                        f" {edge} among them; an output feeds one input"
                    )
                keyword = _keyword(c.to_instance, c.to_port)
                self._keywords[c.to_instance].add(keyword)
                self._routes[c.from_instance, c.from_port] = c.to_instance, keyword
        self._ports: dict[str, tuple[str, str]] = {}
        self._exposed: dict[tuple[str, str], str] = {}
        for name, port in model.ports.items():
            if not name.startswith(f"{topology}.") or port.instance == driver:
                continue
            short = name.removeprefix(f"{topology}.")
            instance = model.instances[port.instance]
            if port.port in {p.name for p in model.components[instance.component].outputs}:
                if (port.instance, port.port) in self._routes:
                    raise ValueError(
                        f"{_name(port.instance)}.{port.port} routes to an input and is the"
                        f" sub-topology's port {short}; an output feeds one or the other"
                    )
                self._exposed[port.instance, port.port] = short
                continue
            keyword = _keyword(port.instance, port.port)
            self._ports[short] = port.instance, keyword
            self._keywords[port.instance].add(keyword)
        self._outputs = {m: [p.name for p in model.components[model.instances[m].component].outputs] for m in members}
        self.algorithms = {}
        self._held: dict[str, dict[str, Any]] = {}
        self._plan: tuple[tuple[_Member, ...], ...] = ()

    def boot(self, parameters: Mapping[str, Any]) -> None:
        """Builds every algorithm afresh on its parameters, with no input written.

        Args:
            parameters: each algorithm's parameters, by its instance's name.
        """
        self.algorithms = {_name(m): cls(parameters[_name(m)]) for m, cls in self._classes.items()}
        self._held = {m: {} for m in self._classes}
        self._plan = tuple(tuple(self._member(m) for m in group) for group in self._members)

    def _member(self, member: str) -> _Member:
        """A member as a frame runs it, planned once per boot.

        Args:
            member: its qualified name.

        Returns:
            Its plan.
        """
        ports = list(enumerate(self._outputs[member]))
        routed = tuple(
            (index, self._held[self._routes[member, port][0]], self._routes[member, port][1])
            for index, port in ports
            if (member, port) in self._routes
        )
        exposed = tuple(
            (index, self._exposed[member, port]) for index, port in ports if (member, port) in self._exposed
        )
        name = _name(member)
        return _Member(
            member, name, self.algorithms[name].step, self._held[member], len(self._keywords[member]), routed, exposed
        )

    def write(self, port: str, value: Any) -> None:
        """Writes a sub-topology input, which its instance holds until the next write.

        Args:
            port: the sub-topology's port, `<role>In`.
            value: the value, in the port's FPP type.
        """
        instance, keyword = self._ports[port]
        self._held[instance][keyword] = value

    def run(self, t: float, fired: Sequence[int]) -> Frame:
        """Runs each member of each fired rate group, in order, routing its outputs.

        Args:
            t: s, the frame's time.
            fired: the position in `rate_groups` of each rate group that runs, in order.

        Returns:
            Each member's telemetry tuple, with its instance's name, in the order run, and the
            latest value written to each sub-topology output port.

        Raises:
            RuntimeError: a member's input has never been written, naming its port.
        """
        telemetry = []
        exposed = {}
        for group in fired:
            for member, name, step, inputs, wanted, routed, exposed_ports in self._plan[group]:
                if len(inputs) < wanted:
                    unwritten = sorted(self._keywords[member] - set(inputs))
                    names = [f"{name}.{k}In" for k in unwritten]
                    raise RuntimeError(f"inputs {names} have not been written at t = {t} s")
                outputs, tlm = step(t, **inputs)
                for index, held, keyword in routed:
                    if outputs[index] is not None:
                        held[keyword] = outputs[index]
                for index, port in exposed_ports:
                    if outputs[index] is not None:
                        exposed[port] = outputs[index]
                telemetry.append(MemberTelemetry(name, tlm))
        return Frame(telemetry, exposed)
