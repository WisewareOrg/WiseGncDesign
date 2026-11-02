"""MRP attitude math for grading recorded runs against truth.

Convention (Schaub & Junkins, Basilisk's own): `sigma_BN` is the modified Rodrigues parameter
set of frame B with respect to frame N. Every function accepts one MRP of shape `(3,)` or a batch
of shape `(N, 3)` and broadcasts over the leading dimension.

Subtraction composes through unit quaternions, which keeps it well-conditioned for any pair of
inputs, including two descriptions of nearly the same attitude on opposite shadow sets.
"""

import numpy as np

__all__ = ["angle", "from_quaternion", "subtract", "to_quaternion"]


def to_quaternion(sigma: np.ndarray) -> np.ndarray:
    """The unit quaternion `[q0, q1, q2, q3]` (scalar first) of an MRP set:
    `q0 = (1 - |sigma|^2) / (1 + |sigma|^2)`, `q_vec = 2 sigma / (1 + |sigma|^2)`.

    Returns shape `(4,)` for one MRP, `(N, 4)` for a batch.
    """
    sigma = np.asarray(sigma, dtype=float)
    s2 = np.sum(sigma * sigma, axis=-1, keepdims=True)
    return np.concatenate(((1.0 - s2) / (1.0 + s2), 2.0 * sigma / (1.0 + s2)), axis=-1)


def from_quaternion(q: np.ndarray) -> np.ndarray:
    """The MRP set of a unit quaternion `[q0, q1, q2, q3]` (scalar first), taken on the branch
    with `|sigma| <= 1`: `sigma = q_vec / (1 + q0)` after choosing the sign with `q0 >= 0`.

    Returns shape `(3,)` for one quaternion, `(N, 3)` for a batch.
    """
    q = np.asarray(q, dtype=float)
    q = np.where(q[..., :1] < 0.0, -q, q)
    return q[..., 1:] / (1.0 + q[..., :1])


def _quaternion_product(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Hamilton product `p ⊗ q`, scalar first: the rotation `q` followed by the rotation `p`
    in the successive-frame (Schaub & Junkins) sense."""
    p0, pv = p[..., :1], p[..., 1:]
    q0, qv = q[..., :1], q[..., 1:]
    scalar = p0 * q0 - np.sum(pv * qv, axis=-1, keepdims=True)
    vector = p0 * qv + q0 * pv - np.cross(pv, qv)
    return np.concatenate((scalar, vector), axis=-1)


def subtract(sigma1: np.ndarray, sigma2: np.ndarray) -> np.ndarray:
    """`sigma1 ⊖ sigma2`: the MRP of frame 1 relative to frame 2, where `sigma1` is frame 1
    with respect to N and `sigma2` is frame 2 with respect to N, so that
    `[1 2] = [1 N][2 N]^T`. The result satisfies `|sigma| <= 1`.

    For a run, `subtract(truth, estimate)` is the attitude error.
    """
    q1 = to_quaternion(sigma1)
    q2 = to_quaternion(sigma2)
    q2_conjugate = q2 * np.array([1.0, -1.0, -1.0, -1.0])
    return from_quaternion(_quaternion_product(q1, q2_conjugate))


def angle(sigma: np.ndarray) -> np.ndarray:
    """The principal rotation angle, in rad, of an MRP set: `4 atan(|sigma|)`."""
    sigma = np.asarray(sigma, dtype=float)
    return 4.0 * np.arctan(np.linalg.norm(sigma, axis=-1))
