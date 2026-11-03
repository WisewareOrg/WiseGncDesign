"""One raw IMU reading in the body frame: the dead reckoner's sample."""

from dataclasses import dataclass

import numpy as np

__all__ = ["ImuSample"]


@dataclass(frozen=True, slots=True)
class ImuSample:
    """One raw IMU reading, already rotated into the body frame by the host.

    Attributes:
        t: s, the time the reading applies at.
        omega_B: (3,) rad/s, angular rate of B with respect to N, in B.
        accel_B: (3,) m/s^2, non-gravitational acceleration, in B.
    """

    t: float
    omega_B: np.ndarray
    accel_B: np.ndarray
