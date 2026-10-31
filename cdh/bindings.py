"""The C&DH partition's data dictionary: for each algorithm, which neutral input role feeds
which of its sample fields, and which of its state fields feeds which neutral output role.
Transport-independent: no message type, payload field name, reader or writer here — a transport
under `cdh/<transport>/` resolves this dictionary against its own wire formats."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample


@dataclass(frozen=True)
class InputBinding:
    """One field of the algorithm's sample, supplied by one neutral input role. `frame` names
    a frame transform the transport applies before the value reaches the algorithm (e.g.
    `"platform_to_body"`); `None` means the value needs no transform."""

    role: str
    algorithm_field: str
    frame: str | None = None


@dataclass(frozen=True)
class OutputBinding:
    """One field of the algorithm's state, delivered to one neutral output role."""

    algorithm_field: str
    role: str


@dataclass(frozen=True)
class AlgorithmBinding:
    """Everything transport-independent about hosting one algorithm: how to build it, and its
    data dictionary of input and output fields."""

    sample_type: type
    make_algorithm: Callable[[float, dict], Any]
    inputs: list[InputBinding]
    outputs: list[OutputBinding]


IMU_DEAD_RECKONING_BINDING = AlgorithmBinding(
    sample_type=ImuSample,
    make_algorithm=lambda t0, init: ImuDeadReckoner(
        init["sigma0_BN"], init["r0_N"], init["v0_N"], t0, init["mu"]
    ),
    inputs=[
        InputBinding(role="imu", algorithm_field="omega_B", frame="platform_to_body"),
        InputBinding(role="imu", algorithm_field="accel_B", frame="platform_to_body"),
    ],
    outputs=[
        OutputBinding(algorithm_field="sigma_BN", role="navAtt"),
        OutputBinding(algorithm_field="r_N", role="navTrans"),
        OutputBinding(algorithm_field="v_N", role="navTrans"),
    ],
)
