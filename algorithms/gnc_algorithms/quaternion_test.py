"""The compiled quaternion math against SciPy's, on random unit quaternions."""

import numpy as np
from scipy.spatial.transform import Rotation

from gnc_algorithms.quaternion import dcm_NB, multiply

QUATERNIONS = Rotation.random(200, random_state=5).as_quat(scalar_first=True)
"""Unit quaternions, W X Y Z, of both signs of W."""


def test_the_dcm_is_scipy_s_rotation_matrix():
    """[NB] of q is SciPy's matrix of the same quaternion, taking body vectors into N."""
    for q in QUATERNIONS:
        expected = Rotation.from_quat(q, scalar_first=True).as_matrix()
        np.testing.assert_allclose(dcm_NB(q), expected, rtol=0, atol=1e-15)


def test_the_product_is_scipy_s_composition():
    """The product p (x) q is the rotation q then p, as SciPy composes them, to its sign."""
    for p, q in zip(QUATERNIONS, QUATERNIONS[::-1], strict=True):
        composed = Rotation.from_quat(p, scalar_first=True) * Rotation.from_quat(
            q, scalar_first=True
        )
        expected = composed.as_quat(scalar_first=True, canonical=False)
        product = multiply(p, q)
        sign = np.sign(product @ expected)
        np.testing.assert_allclose(product, sign * expected, rtol=0, atol=1e-15)
