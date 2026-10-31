import numpy as np
import pytest
from gnc_algorithms import mrp


def test_dcm_at_zero_is_identity():
    np.testing.assert_allclose(mrp.dcm_NB(np.zeros(3)), np.eye(3), atol=1e-12)


def test_b_matrix_at_zero_is_identity():
    np.testing.assert_allclose(mrp.B(np.zeros(3)), np.eye(3), atol=1e-12)


def test_shadow_is_self_inverse():
    sigma = np.array([0.2, -0.1, 0.4])
    np.testing.assert_allclose(mrp.shadow(mrp.shadow(sigma)), sigma, atol=1e-9)


def test_shadow_has_reciprocal_norm():
    sigma = np.array([0.2, -0.1, 0.4])
    assert np.linalg.norm(mrp.shadow(sigma)) == pytest.approx(1.0 / np.linalg.norm(sigma))


def test_angle_at_zero_is_zero():
    assert mrp.angle(np.zeros(3)) == pytest.approx(0.0)


def test_angle_at_unit_norm_is_pi():
    # |sigma| = 1 <=> tan(theta/4) = 1 <=> theta = pi
    assert mrp.angle(np.array([1.0, 0.0, 0.0])) == pytest.approx(np.pi)


def test_subtract_from_self_is_zero():
    sigma = np.array([0.1, 0.2, -0.3])
    np.testing.assert_allclose(mrp.subtract(sigma, sigma), np.zeros(3), atol=1e-9)


def test_compose_matches_dcm_product():
    sigma1 = np.array([0.1, 0.0, 0.0])
    sigma2 = np.array([0.0, 0.15, 0.0])
    composed = mrp.compose(sigma1, sigma2)

    # C_BN(composed) should equal C_BN(sigma2) @ C_BN(sigma1) (apply sigma1 then sigma2).
    expected = mrp.dcm_NB(sigma2).T @ mrp.dcm_NB(sigma1).T
    actual = mrp.dcm_NB(composed).T
    np.testing.assert_allclose(actual, expected, atol=1e-9)
