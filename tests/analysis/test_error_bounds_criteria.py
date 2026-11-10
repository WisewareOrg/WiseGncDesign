"""The allowed-failures rule and the worst-error metrics of `gnc_analysis.error_bounds`."""

import numpy as np
import pytest

from gnc_analysis.error_bounds import (
    allowed_failures,
    worst_attitude_error_rad,
    worst_position_error_m,
    worst_velocity_error_m_s,
)


def _mrp_about_z(angle_rad: np.ndarray) -> np.ndarray:
    """The MRPs of rotations about the z axis.

    Args:
        angle_rad: the rotation angles in rad.

    Returns:
        (N, 3) MRPs.
    """
    sigma = np.zeros((len(angle_rad), 3))
    sigma[:, 2] = np.tan(np.asarray(angle_rad) / 4.0)
    return sigma


@pytest.mark.parametrize(
    ("n", "p", "c", "expected"),
    [
        (852, 0.99, 0.90, 4),
        (852, 0.9973, 0.90, 0),
        (851, 0.9973, 0.90, None),
    ],
)
def test_allowed_failures_matches_the_known_values(
    n: int, p: float, c: float, expected: int | None
) -> None:
    """The rule reproduces the proposal's table, including the no-such-k case as None.

    Args:
        n: the run count.
        p: the reliability.
        c: the confidence.
        expected: the allowed failures, or None.
    """
    assert allowed_failures(n, p, c) == expected


def test_worst_attitude_error_is_the_largest_sample_error():
    """The metric is the maximum over samples of the truth-to-estimate rotation angle."""
    truth = _mrp_about_z(np.array([0.3, 0.3, 0.3, 0.3]))
    est = _mrp_about_z(np.array([0.3, 0.3 + 0.002, 0.3 - 0.0005, 0.3 + 0.001]))
    run = {"truth/sigma_BN": truth, "est/sigma_BN": est}

    assert worst_attitude_error_rad(run) == pytest.approx(0.002, abs=1e-9)


def test_worst_velocity_error_is_the_largest_sample_error():
    """The metric is the maximum over samples of |v_truth - v_est|."""
    truth = np.full((3, 3), 7600.0)
    est = truth + np.array([[0.0, 0.0, 0.0], [3.0, 4.0, 0.0], [1.0, 0.0, 0.0]])
    run = {"truth/v_N": truth, "est/v_BN_N": est}

    assert worst_velocity_error_m_s(run) == pytest.approx(5.0)


def test_worst_position_error_is_the_largest_sample_error():
    """The metric is the maximum over samples of |r_truth - r_est|."""
    truth = np.full((3, 3), 6.9e6)
    est = truth + np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 6.0, 8.0]])
    run = {"truth/r_N": truth, "est/r_BN_N": est}

    assert worst_position_error_m(run) == pytest.approx(10.0)
