"""A configuration's algorithm members: the instances its GNC sub-topology's rate groups run.

The sub-topology is `<configuration>.Gnc`. Its one `Svc.RateGroupDriver` drives its rate groups in
`CycleOut` order, and each rate group runs its members in `RateGroupMemberOut` order. Both builds
read the members here: the Python build's GNC partition, which runs them, and the harness, which
reads each member's component's claims and parameters for either build.
"""

from fsw.codegen.fpp_model import Instance, Model

__all__ = ["DRIVER", "members"]

DRIVER = "Svc.RateGroupDriver"
"""The component type of a sub-topology's rate group driver."""


def members(model: Model, configuration: str) -> dict[str, tuple[Instance, ...]]:
    """Each rate group of a configuration's GNC sub-topology, with the members it runs.

    Args:
        model: the model holding the sub-topology `<configuration>.Gnc`.
        configuration: the configuration, the name of its GNC sub-topology.

    Returns:
        Each rate group's qualified name, in its driver's `CycleOut` order, with its members, in
        its `RateGroupMemberOut` order.

    Raises:
        ValueError: the sub-topology has other than one rate group driver, naming them.
    """
    topology = f"{configuration}.Gnc"
    connections = model.topologies[topology]
    ends = {c.from_instance for c in connections} | {c.to_instance for c in connections}
    drivers = sorted(i for i in ends if model.instances[i].component == DRIVER)
    if len(drivers) != 1:
        raise ValueError(f"{topology} has {len(drivers)} rate group drivers: {drivers}")
    [driver] = drivers
    # The model sorts connections by their from-port's number, so each filter keeps that order.
    groups = [c.to_instance for c in connections if (c.from_instance, c.from_port) == (driver, "CycleOut")]
    return {
        group: tuple(
            model.instances[c.to_instance]
            for c in connections
            if (c.from_instance, c.from_port) == (group, "RateGroupMemberOut")
        )
        for group in groups
    }
