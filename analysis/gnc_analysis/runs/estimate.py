"""The flight software's estimate in a run file."""

from dataclasses import dataclass

import numpy as np

from gnc_analysis.runs.dataset import channel

__all__ = ["Estimate"]


@dataclass(frozen=True)
class Estimate:
    """The flight software's estimate, one row per sample of `Run.t_s`. Read from group `est/`.

    Attributes:
        sigma_BN: (N, 3) MRP of B with respect to N.
        r_N: (N, 3) m, inertial position.
        v_N: (N, 3) m/s, inertial velocity.
    """

    sigma_BN: np.ndarray = channel("MRP")
    r_N: np.ndarray = channel("m")
    v_N: np.ndarray = channel("m/s")
