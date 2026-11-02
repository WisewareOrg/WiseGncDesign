"""`gnc_analysis.mrp` against an oracle built from axis-angle DCMs, which shares no code with
either MRP implementation in this repository."""

import numpy as np
import pytest

from gnc_analysis import mrp


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def _dcm_from_axis_angle(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """[BN] for B rotated from N by `angle_rad` about unit `axis` (Schaub & Junkins 3.62)."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return c * np.eye(3) + (1.0 - c) * np.outer(axis, axis) - s * _skew(axis)


def _mrp_from_axis_angle(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    return np.tan(angle_rad / 4.0) * axis


def _shadow(sigma: np.ndarray) -> np.ndarray:
    return -sigma / (sigma @ sigma)


def _relative_angle(dcm1: np.ndarray, dcm2: np.ndarray) -> float:
    """Principal angle of [1 2] = [1 N][2 N]^T, from its trace."""
    cos_angle = (np.trace(dcm1 @ dcm2.T) - 1.0) / 2.0
    return float(np.arccos(np.clip(cos_angle, -1.0, 1.0)))


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


@pytest.mark.parametrize(
    ("axis1", "angle1", "axis2", "angle2"),
    [
        ([1.0, 0.3, -0.2], 0.7, [-0.4, 1.0, 0.5], 1.9),
        ([0.2, -0.9, 0.4], 2.8, [0.6, 0.1, 0.8], 0.4),
        ([0.5, 0.5, -0.7], 3.0, [0.5, 0.5, -0.7], 2.95),
    ],
)
def test_subtract_matches_the_dcm_oracle_with_neither_argument_zero(axis1, angle1, axis2, angle2):
    a1, a2 = _unit(axis1), _unit(axis2)
    dcm1, dcm2 = _dcm_from_axis_angle(a1, angle1), _dcm_from_axis_angle(a2, angle2)

    relative = mrp.subtract(_mrp_from_axis_angle(a1, angle1), _mrp_from_axis_angle(a2, angle2))

    # [1 2] from the result, rebuilt through the oracle's own axis-angle form.
    angle = mrp.angle(relative)
    expected_angle = _relative_angle(dcm1, dcm2)
    assert angle == pytest.approx(expected_angle, abs=1e-12)
    np.testing.assert_allclose(
        _dcm_from_axis_angle(_unit(relative), angle), dcm1 @ dcm2.T, atol=1e-12
    )


@pytest.mark.parametrize("error_rad", [0.0, 1e-6])
def test_subtract_across_opposite_shadow_sets_recovers_a_small_error(error_rad):
    axis = _unit([0.3, -0.5, 0.8])
    near_pi = np.pi - 1e-3
    truth = _mrp_from_axis_angle(axis, near_pi)
    estimate = _shadow(_mrp_from_axis_angle(axis, near_pi + error_rad))

    assert np.linalg.norm(truth) < 1.0 < np.linalg.norm(estimate)
    assert mrp.angle(mrp.subtract(truth, estimate)) == pytest.approx(error_rad, abs=1e-12)


def test_subtract_result_lies_on_the_short_branch():
    axis = _unit([1.0, 2.0, 3.0])
    relative = mrp.subtract(_mrp_from_axis_angle(axis, 2.5), _mrp_from_axis_angle(-axis, 1.5))

    assert np.linalg.norm(relative) <= 1.0
    assert mrp.angle(relative) == pytest.approx(2.0 * np.pi - 4.0, abs=1e-12)


def test_subtract_broadcasts_over_a_batch():
    rng = np.random.default_rng(3)
    sigma1 = rng.uniform(-0.5, 0.5, (7, 3))
    sigma2 = rng.uniform(-0.5, 0.5, (7, 3))

    batched = mrp.subtract(sigma1, sigma2)

    assert batched.shape == (7, 3)
    for i in range(7):
        np.testing.assert_allclose(batched[i], mrp.subtract(sigma1[i], sigma2[i]), atol=1e-15)


def test_quaternion_round_trip_keeps_the_short_branch():
    sigma = np.array([0.2, -0.4, 0.1])

    np.testing.assert_allclose(mrp.from_quaternion(mrp.to_quaternion(sigma)), sigma, atol=1e-15)
    np.testing.assert_allclose(
        mrp.from_quaternion(mrp.to_quaternion(_shadow(sigma))), sigma, atol=1e-15
    )


@pytest.mark.parametrize(("norm", "expected"), [(0.0, 0.0), (1.0, np.pi), (np.tan(0.25), 1.0)])
def test_angle_is_four_atan_of_the_norm(norm, expected):
    assert mrp.angle(norm * _unit([1.0, -1.0, 2.0])) == pytest.approx(expected, abs=1e-15)
