"""The IMU's output in a run file."""

from dataclasses import dataclass

import numpy as np

from gnc_analysis.runs.dataset import channel

__all__ = ["ImuReadings"]


@dataclass(frozen=True)
class ImuReadings:
    """The IMU's own output, in its sensor (platform) frame P, one row per sample of
    `Run.t_s`. Read from group `imu/`.

    Attributes:
        gyro_P: (N, 3) rad/s, angular rate in P.
        accel_P: (N, 3) m/s^2, non-gravitational acceleration in P.
    """

    gyro_P: np.ndarray = channel("rad/s")
    accel_P: np.ndarray = channel("m/s^2")
