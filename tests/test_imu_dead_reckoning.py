import numpy as np
import pytest
from gnc_algorithms import mrp
from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample


def _run_constant_rate(omega_B, total_t, n_steps, sigma0=None):
    sigma0 = np.zeros(3) if sigma0 is None else sigma0
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, t0=0.0)
    dt = total_t / n_steps
    state = reckoner.state
    for i in range(1, n_steps + 1):
        state = reckoner.step(ImuSample(t=i * dt, omega_B=np.asarray(omega_B), accel_B=np.zeros(3)))
    return state


def test_constant_rate_about_body_axis_matches_analytic_mrp():
    omega = 0.5  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = 1.0

    state = _run_constant_rate(omega * axis, total_t, n_steps=2000)

    theta = omega * total_t
    expected = np.tan(theta / 4.0) * axis
    np.testing.assert_allclose(state.sigma_BN, expected, atol=1e-6)


def test_zero_input_leaves_state_unchanged():
    sigma0 = np.array([0.1, -0.05, 0.2])
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, t0=0.0)

    state = reckoner.step(ImuSample(t=1.0, omega_B=np.zeros(3), accel_B=np.zeros(3)))

    np.testing.assert_allclose(state.sigma_BN, sigma0, atol=1e-12)
    np.testing.assert_allclose(state.dv_N, np.zeros(3), atol=1e-12)
    assert state.t == pytest.approx(1.0)


def test_rotation_past_180_degrees_switches_to_shadow_set():
    omega = 1.0  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = np.pi * 1.2  # theta = 1.2*pi > pi

    state = _run_constant_rate(omega * axis, total_t, n_steps=4000)

    assert np.linalg.norm(state.sigma_BN) <= 1.0

    theta = omega * total_t
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    skew_axis = np.array(
        [[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]]
    )
    expected_dcm_bn = cos_t * np.eye(3) + (1.0 - cos_t) * np.outer(axis, axis) - sin_t * skew_axis

    actual_dcm_bn = mrp.dcm_NB(state.sigma_BN).T
    np.testing.assert_allclose(actual_dcm_bn, expected_dcm_bn, atol=1e-5)


def test_constant_acceleration_with_zero_rate_gives_dv_equal_to_a_times_t():
    accel = np.array([0.3, -0.1, 0.05])
    total_t = 10.0
    reckoner = ImuDeadReckoner(sigma0_BN=np.zeros(3), t0=0.0)

    state = reckoner.step(ImuSample(t=total_t, omega_B=np.zeros(3), accel_B=accel))

    np.testing.assert_allclose(state.dv_N, accel * total_t, atol=1e-9)


def test_kinematics_match_dcm_derivative_for_nonaligned_rate():
    # For sigma not parallel to omega, B(sigma)'s cross-product term is the only one that
    # can couple the axes; a lone-axis-aligned case (as above) cannot exercise its sign.
    # C_BN's time derivative obeys Cdot_BN = -[omega_B x] C_BN regardless of attitude
    # parameterization (Schaub & Junkins eq. 3.28); check the propagator against that
    # independent identity by finite difference.
    sigma0 = np.array([0.1, 0.0, 0.0])
    omega = np.array([0.0, 0.0, 0.3])
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, t0=0.0)
    dt = 1e-5

    state = reckoner.step(ImuSample(t=dt, omega_B=omega, accel_B=np.zeros(3)))

    c0 = mrp.dcm_NB(sigma0).T
    c1 = mrp.dcm_NB(state.sigma_BN).T
    cdot_finite_difference = (c1 - c0) / dt

    skew_omega = np.array(
        [[0.0, -omega[2], omega[1]], [omega[2], 0.0, -omega[0]], [-omega[1], omega[0], 0.0]]
    )
    expected_cdot = -skew_omega @ c0

    np.testing.assert_allclose(cdot_finite_difference, expected_cdot, atol=1e-3)


def test_non_positive_dt_raises():
    reckoner = ImuDeadReckoner(sigma0_BN=np.zeros(3), t0=5.0)

    with pytest.raises(ValueError):
        reckoner.step(ImuSample(t=5.0, omega_B=np.zeros(3), accel_B=np.zeros(3)))

    with pytest.raises(ValueError):
        reckoner.step(ImuSample(t=4.0, omega_B=np.zeros(3), accel_B=np.zeros(3)))
