"""MRP math needed by the attitude-error analysis, reimplemented locally: uses numpy only; the
analysis package imports nothing from gnc_algorithms, gnc_cdh or Basilisk. Follows Basilisk's
convention (Schaub & Junkins): sigma_BN, body wrt inertial.

Every function broadcasts over a leading batch dimension: a shape-(3,) or shape-(N, 3) array of
MRP vectors both work.
"""

import numpy as np


def subtract(sigma1: np.ndarray, sigma2: np.ndarray) -> np.ndarray:
    """sigma1 (-) sigma2: the MRP of the attitude described by sigma1 relative to the attitude
    described by sigma2 (Schaub & Junkins MRP subtraction, equivalent to composing sigma1 with
    the inverse of sigma2)."""
    sigma1 = np.asarray(sigma1, dtype=float)
    sigma2 = np.asarray(sigma2, dtype=float)

    s1_sq = np.sum(sigma1 * sigma1, axis=-1, keepdims=True)
    s2_sq = np.sum(sigma2 * sigma2, axis=-1, keepdims=True)
    dot = np.sum(sigma1 * sigma2, axis=-1, keepdims=True)
    cross = np.cross(sigma1, sigma2)

    numerator = (1 - s2_sq) * sigma1 - (1 - s1_sq) * sigma2 + 2 * cross
    denominator = 1 + s1_sq * s2_sq + 2 * dot
    return numerator / denominator


def shadow(sigma: np.ndarray) -> np.ndarray:
    """The shadow-set MRP: same attitude, |sigma| <= 1 whenever the input's |sigma| >= 1."""
    sigma = np.asarray(sigma, dtype=float)
    mag_sq = np.sum(sigma * sigma, axis=-1, keepdims=True)
    return -sigma / mag_sq


def angle(sigma: np.ndarray) -> np.ndarray:
    """The rotation angle (radians) an MRP represents: 4*atan(|sigma|)."""
    sigma = np.asarray(sigma, dtype=float)
    mag = np.linalg.norm(sigma, axis=-1)
    return 4.0 * np.arctan(mag)
