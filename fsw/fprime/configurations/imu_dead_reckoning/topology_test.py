"""The WiseFsw deployment's health instances, its rate groups, take base IDs from `Ids.healthBase`.

GroundLink does not downlink telemetry at or above that base, so a rate group outside the range
would reach the run file, and any other instance inside it would be lost. Needs the F´ framework
clone `just _sync` fetches, not an F´ build.
"""

from fsw.codegen.deployment import FPP_FILES
from fsw.codegen.fpp_model import read

_RATE_GROUPS = {"Svc.PassiveRateGroup", "Svc.ActiveRateGroup"}
"""F´'s rate-group components, the deployment's health instances."""


def test_the_rate_groups_and_nothing_else_take_health_base_ids():
    """Every rate group's base ID is at or above `Ids.healthBase`, and every other one is below."""
    model = read(FPP_FILES)
    health_base = model.constants["Ids.healthBase"]

    for instance in model.instances.values():
        rate_group = instance.component in _RATE_GROUPS
        assert (instance.base_id >= health_base) == rate_group, (
            f"{instance.name}, a {instance.component} at base ID {instance.base_id:#x}: rate groups"
            f" take base IDs from Ids.healthBase ({health_base:#x}) up, and nothing else does"
        )
