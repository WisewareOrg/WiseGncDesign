"""Plant truth in a run file."""

from dataclasses import dataclass

import numpy as np

from gnc_analysis.runs.dataset import channel

__all__ = ["Truth"]


@dataclass(frozen=True)
class Truth:
    """Plant truth, one row per sample of `Run.t_s`. Read from group `truth/`.

    Attributes:
        sigma_BN: (N, 3) MRP of the body frame B with respect to the inertial frame N.
        omega_BN_B: (N, 3) rad/s, angular rate of B with respect to N, in B.
        r_N: (N, 3) m, inertial position.
        v_N: (N, 3) m/s, inertial velocity.
    """

    sigma_BN: np.ndarray = channel("MRP")
    omega_BN_B: np.ndarray = channel("rad/s")
    r_N: np.ndarray = channel("m")
    v_N: np.ndarray = channel("m/s")
