"""The dead reckoner's state at one instant."""

from dataclasses import dataclass

import numpy as np

__all__ = ["DeadReckoningState"]


@dataclass(frozen=True, slots=True)
class DeadReckoningState:
    """The estimator's state at one instant. Its arrays are read-only.

    Attributes:
        t: s, the time the state applies at.
        sigma_BN: (3,) MRP of B with respect to N, with |sigma_BN| <= 1.
        r_N: (3,) m, inertial position.
        v_N: (3,) m/s, inertial velocity.
    """

    t: float
    sigma_BN: np.ndarray
    r_N: np.ndarray
    v_N: np.ndarray
