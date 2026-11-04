"""Modified Rodrigues parameter (MRP) attitude math: the kinematics matrix, the DCM, the shadow set.

The MRP is `sigma_BN`, frame B with respect to frame N (Schaub & Junkins).

With [~sigma] the cross-product matrix of sigma and s^2 = |sigma|^2:
B(sigma) = (1 - s^2) I + 2 [~sigma] + 2 sigma sigma^T, so dsigma/dt = 1/4 B(sigma) omega_BN_B;
[NB] = I + (8 [~sigma]^2 + 4 (1 - s^2) [~sigma]) / (1 + s^2)^2; and the shadow set
-sigma / s^2 describes the same attitude with the reciprocal norm. Each function is compiled
with numba on its first call and cached on disk.
"""

import numpy as np
from numba import njit

__all__ = ["B", "dcm_NB", "shadow"]


@njit(cache=True)
def _skew(v: np.ndarray) -> np.ndarray:
    """The (3, 3) cross-product matrix [~v] of a (3,) array `v`, so that [~v] u = v x u."""
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


@njit(cache=True)
def B(sigma: np.ndarray) -> np.ndarray:
    """The (3, 3) MRP kinematics matrix of the (3,) MRP `sigma`.

    dsigma/dt = 1/4 B @ omega, with omega the angular rate of B with respect to N, in B (rad/s).
    """
    s2 = float(sigma @ sigma)
    return (1.0 - s2) * np.eye(3) + 2.0 * _skew(sigma) + 2.0 * np.outer(sigma, sigma)


@njit(cache=True)
def dcm_NB(sigma: np.ndarray) -> np.ndarray:
    """The (3, 3) DCM [NB] of the (3,) MRP `sigma` = sigma_BN.

    It rotates a B-frame vector into N: v_N = [NB] v_B.
    """
    s2 = float(sigma @ sigma)
    sk = _skew(sigma)
    return np.eye(3) + (8.0 * (sk @ sk) + 4.0 * (1.0 - s2) * sk) / (1.0 + s2) ** 2


@njit(cache=True)
def shadow(sigma: np.ndarray) -> np.ndarray:
    """The shadow set -sigma / |sigma|^2: the same attitude with the reciprocal norm.

    `sigma` is a nonzero (3,) MRP.
    """
    s2 = float(sigma @ sigma)
    return -sigma / s2
