"""What each hosted algorithm reads and writes, as Basilisk message fields: one `Binding` per
algorithm, by the name `make_fsw` builds it under."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from Basilisk.architecture import messaging

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample

__all__ = ["BINDINGS", "Binding"]


@dataclass(frozen=True)
class Binding:
    """One algorithm's declaration of what it reads and what it writes.

    Attributes:
        algorithm: the algorithm class, built as `algorithm(t0=..., **init)`, exposing `state`
            and `step(sample)`.
        sample: the dataclass `step` takes: field `t` (s) plus one field per entry of `inputs`.
        inputs: sample field to the `(input role, message field)` it is copied from.
        outputs: state field to the `(output message, message field)` it is copied to.
        messages: output message name to its Basilisk message type.
    """

    algorithm: type
    sample: type
    inputs: Mapping[str, tuple[str, str]]
    outputs: Mapping[str, tuple[str, str]]
    messages: Mapping[str, type]


BINDINGS: Mapping[str, Binding] = MappingProxyType(
    {
        "imu_dead_reckoning": Binding(
            algorithm=ImuDeadReckoner,
            sample=ImuSample,
            inputs={"omega_P": ("imu", "AngVelPlatform"), "accel_P": ("imu", "AccelPlatform")},
            outputs={
                "sigma_BN": ("nav_att", "sigma_BN"),
                "r_N": ("nav_trans", "r_BN_N"),
                "v_N": ("nav_trans", "v_BN_N"),
            },
            messages={"nav_att": messaging.NavAttMsg, "nav_trans": messaging.NavTransMsg},
        ),
    }
)
