"""The WiseFsw deployment records the telemetry of every instance but those it names as unrecorded.

The topology's telemetry rule lists the instances it connects, so an instance left off it writes
telemetry the ground never records. Needs the F´ framework clone `just _sync` fetches, not an F´
build.
"""

import pytest

from fsw.codegen.deployment import FPP_FILES
from fsw.codegen.fpp_model import Connection, Model, read

_UNRECORDED = {"ImuDeadReckoning.navRateGroup": "health telemetry, deferred (E1)"}
"""The instances whose telemetry is deliberately not connected, each with its reason."""

_TOPOLOGY = "WiseFsw.WiseFsw"
_CLOCK = "WiseFsw.simTime"
_GROUND = "WiseFsw.groundLink"
_FIX = "add it to the topology's telemetry rule, or to _UNRECORDED with a reason"


@pytest.fixture(scope="module")
def model() -> Model:
    """The deployment's model, read once.

    Returns:
        The model.
    """
    return read(FPP_FILES)


def _deployed(connections: tuple[Connection, ...]) -> set[str]:
    """The deployment's instances that can write telemetry.

    FPP requires a time get port on a component with telemetry channels, and the time rule
    connects every such port to the clock, so none is missed.

    Args:
        connections: the deployment's connections.

    Returns:
        Each instance connected to the clock.
    """
    return {c.from_instance for c in connections if c.to_instance == _CLOCK}


def _recorded(connections: tuple[Connection, ...]) -> set[str]:
    """The instances whose telemetry reaches the ground link.

    Args:
        connections: the deployment's connections.

    Returns:
        Each instance connected to the ground link's `tlmIn`.
    """
    return {
        c.from_instance for c in connections if (c.to_instance, c.to_port) == (_GROUND, "tlmIn")
    }


def test_every_instance_with_telemetry_is_recorded_or_named_unrecorded(model: Model):
    """An instance with a channel is connected to the ground link, unless it is in `_UNRECORDED`.

    Args:
        model: the deployment's model.
    """
    connections = model.topologies[_TOPOLOGY]
    recorded = _recorded(connections)

    for instance in sorted(_deployed(connections)):
        if model.components[model.instances[instance].component].channels:
            assert instance in recorded or instance in _UNRECORDED, (
                f"{instance} writes telemetry the ground never records: {_FIX}"
            )


def test_every_unrecorded_instance_is_deployed_and_not_recorded(model: Model):
    """Each `_UNRECORDED` entry is an instance of the deployment whose telemetry is not connected.

    Args:
        model: the deployment's model.
    """
    connections = model.topologies[_TOPOLOGY]
    deployed, recorded = _deployed(connections), _recorded(connections)

    for instance in _UNRECORDED:
        assert instance in deployed, f"{instance} in _UNRECORDED is not in the deployment"
        assert instance not in recorded, (
            f"{instance} in _UNRECORDED is connected to the ground link; remove it from _UNRECORDED"
        )
