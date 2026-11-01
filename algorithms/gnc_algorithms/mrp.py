"""MRP (modified Rodrigues parameter) attitude math, framework-free.

Convention: sigma_BN is the MRP of frame B with respect to frame N (Schaub & Junkins).
dcm_NB(sigma) rotates a body-frame vector into the inertial frame: v_N = dcm_NB(sigma) @ v_B.
"""

import numpy as np


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array(
        [
            [0.0, -v[2], v[1]],
            [v[2], 0.0, -v[0]],
            [-v[1], v[0], 0.0],
        ]
    )


def B(sigma: np.ndarray) -> np.ndarray:
    """MRP rate-kinematics matrix: dsigma/dt = 1/4 B(sigma) @ omega."""
    s2 = float(sigma @ sigma)
    return (1.0 - s2) * np.eye(3) + 2.0 * _skew(sigma) + 2.0 * np.outer(sigma, sigma)


def dcm_NB(sigma: np.ndarray) -> np.ndarray:
    """DCM rotating a body-frame vector into the inertial frame: v_N = dcm_NB(sigma) @ v_B."""
    s2 = float(sigma @ sigma)
    sk = _skew(sigma)
    return np.eye(3) + (8.0 * (sk @ sk) + 4.0 * (1.0 - s2) * sk) / (1.0 + s2) ** 2


def shadow(sigma: np.ndarray) -> np.ndarray:
    """The shadow-set MRP representing the same attitude, with the reciprocal norm."""
    s2 = float(sigma @ sigma)
    return -sigma / s2


def _mrp_from_dcm(c: np.ndarray) -> np.ndarray:
    """Quaternion extraction (Shepperd's method) followed by quaternion-to-MRP, with the
    sign chosen so the scalar part is non-negative and |sigma| <= 1."""
    tr = float(np.trace(c))
    candidates = np.array([tr, c[0, 0], c[1, 1], c[2, 2]])
    largest = int(np.argmax(candidates))
    if largest == 0:
        q0 = 0.5 * np.sqrt(1.0 + tr)
        q1 = (c[1, 2] - c[2, 1]) / (4.0 * q0)
        q2 = (c[2, 0] - c[0, 2]) / (4.0 * q0)
        q3 = (c[0, 1] - c[1, 0]) / (4.0 * q0)
    elif largest == 1:
        q1 = 0.5 * np.sqrt(1.0 + 2.0 * c[0, 0] - tr)
        q0 = (c[1, 2] - c[2, 1]) / (4.0 * q1)
        q2 = (c[0, 1] + c[1, 0]) / (4.0 * q1)
        q3 = (c[0, 2] + c[2, 0]) / (4.0 * q1)
    elif largest == 2:
        q2 = 0.5 * np.sqrt(1.0 + 2.0 * c[1, 1] - tr)
        q0 = (c[2, 0] - c[0, 2]) / (4.0 * q2)
        q1 = (c[0, 1] + c[1, 0]) / (4.0 * q2)
        q3 = (c[1, 2] + c[2, 1]) / (4.0 * q2)
    else:
        q3 = 0.5 * np.sqrt(1.0 + 2.0 * c[2, 2] - tr)
        q0 = (c[0, 1] - c[1, 0]) / (4.0 * q3)
        q1 = (c[0, 2] + c[2, 0]) / (4.0 * q3)
        q2 = (c[1, 2] + c[2, 1]) / (4.0 * q3)
    q = np.array([q0, q1, q2, q3])
    if q[0] < 0.0:
        q = -q
    return q[1:] / (1.0 + q[0])


def compose(sigma1: np.ndarray, sigma2: np.ndarray) -> np.ndarray:
    """Compose two sequential rotations: apply sigma1, then sigma2 (defined relative to the
    frame sigma1 produces)."""
    dcm1 = dcm_NB(sigma1).T  # body-1 wrt N
    dcm2 = dcm_NB(sigma2).T  # body-2 wrt body-1
    return _mrp_from_dcm(dcm2 @ dcm1)


def subtract(sigma1: np.ndarray, sigma2: np.ndarray) -> np.ndarray:
    """sigma1 (-) sigma2: the attitude of frame 1 relative to frame 2."""
    dcm1 = dcm_NB(sigma1).T
    dcm2 = dcm_NB(sigma2).T
    return _mrp_from_dcm(dcm1 @ dcm2.T)


def angle(sigma: np.ndarray) -> float:
    """Rotation angle (rad) represented by an MRP: 4 atan(|sigma|)."""
    return 4.0 * float(np.arctan(np.linalg.norm(sigma)))
