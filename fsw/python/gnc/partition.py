"""The GNC partition: a configuration's GNC sub-topology's algorithms, run as its FPP wires them.

The sub-topology is `<configuration>.Gnc`. Its one `Svc.RateGroupDriver` drives its
`Svc.PassiveRateGroup`s, in `CycleOut` order, and each rate group runs its members in
`RateGroupMemberOut` order; every other connection between its instances carries data. An algorithm
is a class named as its member's FPP component, built at `boot` on its parameters. Its `step` takes
`t`, in s, and a keyword per data input, named as the input port without its trailing `In`, and
returns its `<Name>Outputs` and `<Name>Telemetry` tuples, read by field name. A connection
`A.X -> B.Y` routes `A`'s output `X` to `B`'s input `Y`, as an F´ sync port does: an output reaches
a later member in the same frame, and a `None` output writes nothing, so an input holds the latest
value written to it. A backward edge, into a member that runs no later than `A` in the frame, `A`
itself included, is refused, as is an output feeding more than one input.
A sub-topology `port` other than the driver's is an input the CDH writes.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from fsw.codegen.fpp_model import Model

__all__ = ["GncPartition"]

_DRIVER = "Svc.RateGroupDriver"
"""The component type of the sub-topology's rate group driver."""

_RATE_GROUP = "Svc.PassiveRateGroup"
"""The component type of its rate groups."""


def _name(instance: str) -> str:
    """An instance's name with its module dropped, as the dictionary names it.

    Args:
        instance: its qualified name, such as `ImuDeadReckoning.nav`.

    Returns:
        The name, such as `nav`.
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
            f"{_name(instance)}.{port} is a data input whose name does not end in In, so it"
            " names no step keyword"
        )
    return port.removesuffix("In")


class GncPartition:
    """A configuration's GNC sub-topology's algorithms, wired and ordered as its FPP says.

    Attributes:
        rate_groups: each rate group's qualified name, in its driver's `CycleOut` order; a frame's
            rate groups are named by their position here.
        algorithms: each algorithm `boot` built, by its instance's name, such as `nav`.
    """

    rate_groups: tuple[str, ...]
    algorithms: dict[str, Any]

    def __init__(self, model: Model, configuration: str, classes: Sequence[type]) -> None:
        """Reads the sub-topology's wiring and matches each member to its class.

        Args:
            model: the model holding the sub-topology `<configuration>.Gnc`.
            configuration: the configuration, such as `ImuDeadReckoning`.
            classes: the algorithms' classes, one per member's component, each named as it.

        Raises:
            ValueError: the sub-topology has other than one rate group driver; a member's component
                has no class, or a class no member; a data input is not named `<keyword>In`; a data
                connection is a backward edge; or an output feeds more than one input, naming it.
        """
        topology = f"{configuration}.Gnc"
        connections = model.topologies[topology]
        component = {
            c.from_instance: model.instances[c.from_instance].component for c in connections
        } | {c.to_instance: model.instances[c.to_instance].component for c in connections}
        drivers = sorted(i for i, kind in component.items() if kind == _DRIVER)
        if len(drivers) != 1:
            raise ValueError(f"{topology} has {len(drivers)} rate group drivers: {drivers}")
        [driver] = drivers
        # The model sorts connections by their from-port's number, so each filter keeps that order.
        self.rate_groups = tuple(
            c.to_instance
            for c in connections
            if c.from_instance == driver and c.from_port == "CycleOut"
        )
        self._members = tuple(
            tuple(
                c.to_instance
                for c in connections
                if c.from_instance == group and c.from_port == "RateGroupMemberOut"
            )
            for group in self.rate_groups
        )
        members = {m for group in self._members for m in group}
        by_name = {cls.__name__: cls for cls in classes}
        wanted = {m: model.instances[m].component.rsplit(".", 1)[-1] for m in members}
        missing = sorted(set(wanted.values()) - set(by_name))
        extra = sorted(set(by_name) - set(wanted.values()))
        if missing or extra:
            raise ValueError(
                f"{topology}'s members need the classes {missing} and have none for {extra}"
            )
        self._classes = {m: by_name[name] for m, name in wanted.items()}

        scheduling = {i for i, kind in component.items() if kind in (_DRIVER, _RATE_GROUP)}
        order = {m: n for n, m in enumerate(m for group in self._members for m in group)}
        self._keywords: dict[str, set[str]] = {m: set() for m in members}
        self._routes: dict[tuple[str, str], tuple[str, str]] = {}
        for c in connections:
            if c.from_instance not in scheduling:
                edge = (
                    f"{_name(c.from_instance)}.{c.from_port} -> {_name(c.to_instance)}.{c.to_port}"
                )
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
        for name, port in model.ports.items():
            if name.startswith(f"{topology}.") and port.instance != driver:
                keyword = _keyword(port.instance, port.port)
                self._ports[name.removeprefix(f"{topology}.")] = port.instance, keyword
                self._keywords[port.instance].add(keyword)
        self.algorithms = {}
        self._held: dict[str, dict[str, Any]] = {}

    def boot(self, parameters: Mapping[str, Any]) -> None:
        """Builds every algorithm afresh on its parameters, with no input written.

        Args:
            parameters: each algorithm's parameters, by its instance's name.
        """
        self.algorithms = {_name(m): cls(parameters[_name(m)]) for m, cls in self._classes.items()}
        self._held = {m: {} for m in self._classes}

    def write(self, port: str, value: Any) -> None:
        """Writes a sub-topology input, which its instance holds until the next write.

        Args:
            port: the sub-topology's port, such as `imuIn`.
            value: the value, in the port's FPP type.
        """
        instance, keyword = self._ports[port]
        self._held[instance][keyword] = value

    def run(self, t: float, fired: Sequence[int]) -> list[tuple[str, Any]]:
        """Runs each member of each fired rate group, in order, routing its outputs.

        Args:
            t: s, the frame's time.
            fired: the position in `rate_groups` of each rate group that runs, in order.

        Returns:
            Each member's telemetry tuple, with its instance's name, in the order run.

        Raises:
            RuntimeError: a member's input has never been written, naming its port.
        """
        telemetry = []
        for group in fired:
            for member in self._members[group]:
                inputs = self._held[member]
                unwritten = sorted(self._keywords[member] - set(inputs))
                if unwritten:
                    names = [f"{_name(member)}.{k}In" for k in unwritten]
                    raise RuntimeError(f"inputs {names} have not been written at t = {t} s")
                outputs, tlm = self.algorithms[_name(member)].step(t, **inputs)
                for port, value in outputs._asdict().items():
                    if value is not None and (member, port) in self._routes:
                        target, keyword = self._routes[member, port]
                        self._held[target][keyword] = value
                telemetry.append((_name(member), tlm))
        return telemetry
