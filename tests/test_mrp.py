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


def test_subtract_direction_recovers_sigma1_via_compose():
    # sigma1 (-) sigma2 is defined as the attitude of frame 1 relative to frame 2, so composing
    # it back onto sigma2 should recover sigma1. test_subtract_from_self_is_zero alone cannot
    # tell this convention from its swapped (sigma2 (-) sigma1) counterpart, since both are zero
    # when sigma1 == sigma2.
    sigma1 = np.array([0.1, 0.2, -0.3])
    sigma2 = np.array([-0.2, 0.05, 0.1])

    relative = mrp.subtract(sigma1, sigma2)
    recovered = mrp.compose(sigma2, relative)

    np.testing.assert_allclose(recovered, sigma1, atol=1e-9)


def _dcm_bn_from_axis_angle(axis: np.ndarray, theta: float) -> np.ndarray:
    skew_axis = np.array(
        [[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]]
    )
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return cos_t * np.eye(3) + (1.0 - cos_t) * np.outer(axis, axis) - sin_t * skew_axis


@pytest.mark.parametrize(
    "raw_axis",
    [
        np.array([1.0, 0.3, 0.2]),  # dominant x: selects branch 1
        np.array([0.3, 1.0, 0.2]),  # dominant y: selects branch 2
        np.array([0.3, 0.2, 1.0]),  # dominant z: selects branch 3
    ],
)
def test_compose_near_180_degrees_exercises_non_trace_shepperd_branch(raw_axis):
    # Every other compose/subtract test stays near the identity, where the quaternion
    # extraction's largest-of-four selection always picks the trace branch. A rotation whose
    # angle exceeds 90 degrees makes one axis's own diagonal entry the largest candidate instead,
    # exercising the other three branches. A *principal*-axis rotation would still leave each
    # branch's symmetric off-diagonal sum terms (e.g. C12 + C21) identically zero, so a sign or
    # index error in those terms would pass unnoticed; tilting the axis off-principal makes every
    # term in the chosen branch nonzero.
    axis = raw_axis / np.linalg.norm(raw_axis)
    theta_half = np.radians(85.0)
    sigma_half = np.tan(theta_half / 4.0) * axis

    composed = mrp.compose(sigma_half, sigma_half)

    theta_total = 2.0 * theta_half
    expected_bn = _dcm_bn_from_axis_angle(axis, theta_total)
    actual_bn = mrp.dcm_NB(composed).T
    np.testing.assert_allclose(actual_bn, expected_bn, atol=1e-7)
