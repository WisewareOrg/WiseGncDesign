"""The Basilisk transport's resolution of `cdh.bindings`' data dictionary: the payload field,
message type and mounting each neutral role and field actually needs."""

from dataclasses import dataclass
from typing import Any

import numpy as np
from Basilisk.architecture import messaging

import cdh.bindings as data_dictionary
from cdh.basilisk.algorithm_module import FieldMap

# The neutral frame names cdh.bindings uses, translated to AlgorithmModule's own frame tokens.
_FRAMES = {"platform_to_body": "P->B"}


@dataclass(frozen=True)
class ResolvedBinding:
    """One algorithm's data dictionary, resolved to the Basilisk message fields, reader/writer
    types and mounting `AlgorithmModule` needs to host it. `make_outputs` returns a fresh
    `outputs` dict (new message instances) each call, so each hosted module gets its own."""

    sample_type: type
    make_algorithm: Any
    input_map: list[FieldMap]
    output_map: list[FieldMap]
    mountings: dict[str, np.ndarray]
    make_outputs: Any


IMU_DEAD_RECKONING_BINDING = ResolvedBinding(
    sample_type=data_dictionary.IMU_DEAD_RECKONING_BINDING.sample_type,
    make_algorithm=data_dictionary.IMU_DEAD_RECKONING_BINDING.make_algorithm,
    input_map=[
        FieldMap("imu.AngVelPlatform", "omega_B", frame=_FRAMES["platform_to_body"]),
        FieldMap("imu.AccelPlatform", "accel_B", frame=_FRAMES["platform_to_body"]),
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
