"""Quaternion math the numba-compiled algorithms call, where SciPy cannot be called.

A quaternion is Hamilton, scalar first, W X Y Z. An attitude q of the body frame B with respect to
the inertial frame N takes body-frame vectors into N: v_N = q (x) v_B (x) q*.
"""

import numpy as np
from numba import njit

__all__ = ["dcm_NB", "multiply", "q_dot"]


@njit(cache=True)
def multiply(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """The Hamilton product p (x) q.

    Args:
        p: (4,) quaternion W X Y Z.
        q: (4,) quaternion W X Y Z.

    Returns:
        (4,) p (x) q, W X Y Z; for attitudes, the rotation q followed by p.
    """
    pw, pv, qw, qv = p[0], p[1:], q[0], q[1:]
    vector = pw * qv + qw * pv + np.cross(pv, qv)
    return np.concatenate((np.array([pw * qw - pv @ qv]), vector))


@njit(cache=True)
def q_dot(q: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """The attitude kinematics, dq/dt = 1/2 q (x) (0, omega).

    Args:
        q: (4,) quaternion W X Y Z of the body frame B with respect to the inertial frame N.
        omega: (3,) rad/s, the rate of B with respect to N, in B.

    Returns:
        (4,) dq/dt, 1/s.
    """
    return 0.5 * multiply(q, np.concatenate((np.zeros(1), omega)))


@njit(cache=True)
def dcm_NB(q: np.ndarray) -> np.ndarray:
    """The DCM [NB] of a unit quaternion, rotating a body-frame vector into the inertial frame.

    Args:
        q: (4,) unit quaternion W X Y Z of the body frame B with respect to the inertial frame N.

    Returns:
        (3, 3) [NB], so that v_N = [NB] v_B.
    """
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )
