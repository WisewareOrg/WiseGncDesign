"""`BINDINGS`: each hosted algorithm's `Binding`, by the name `make_fsw` builds it under."""

from collections.abc import Mapping
from types import MappingProxyType

from Basilisk.architecture import messaging

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner
from gnc_cdh.basilisk.binding import Binding

__all__ = ["BINDINGS"]

BINDINGS: Mapping[str, Binding] = MappingProxyType(
    {
        "imu_dead_reckoning": Binding(
            algorithm=ImuDeadReckoner,
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
