"""The Basilisk-host binding for WiseGncDesign's `ImuDeadReckoner`: the message field maps and
mounting that let `AlgorithmModule` host it, independent of any one plant instance."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from Basilisk.architecture import messaging
from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample

from hosts.basilisk.algorithm_module import FieldMap


@dataclass(frozen=True)
class AlgorithmBinding:
    """Everything `AlgorithmModule` needs to host one algorithm, independent of which plant
    instance supplies its messages. `make_outputs` returns a fresh `outputs` dict (new message
    instances) each call, so each hosted module gets its own."""

    sample_type: type
    make_algorithm: Callable[[float, dict], Any]
    input_map: list[FieldMap]
    output_map: list[FieldMap]
    mountings: dict[str, np.ndarray]
    make_outputs: Callable[[], dict[str, tuple[type, Any]]]


IMU_DEAD_RECKONING_BINDING = AlgorithmBinding(
    sample_type=ImuSample,
    make_algorithm=lambda t0, init: ImuDeadReckoner(
        init["sigma0_BN"], init["r0_N"], init["v0_N"], t0, init["mu"]
    ),
    input_map=[
        FieldMap("imu.AngVelPlatform", "omega_B", frame="P->B"),
        FieldMap("imu.AccelPlatform", "accel_B", frame="P->B"),
    ],
    output_map=[
        FieldMap("sigma_BN", "navAtt.sigma_BN"),
        FieldMap("r_N", "navTrans.r_BN_N"),
        FieldMap("v_N", "navTrans.v_BN_N"),
    ],
    mountings={"imu": np.eye(3)},
    make_outputs=lambda: {
        "navAtt": (messaging.NavAttMsgPayload, messaging.NavAttMsg()),
        "navTrans": (messaging.NavTransMsgPayload, messaging.NavTransMsg()),
    },
)
