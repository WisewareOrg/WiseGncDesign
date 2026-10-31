import math

import numpy as np
import pytest
from gnc_algorithms import mrp
from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample

_ZERO3 = np.zeros(3)


def _run_constant_rate(omega_B, total_t, n_steps, sigma0=None, mu=0.0, r0=None, v0=None):
    sigma0 = _ZERO3 if sigma0 is None else sigma0
    r0 = _ZERO3 if r0 is None else r0
    v0 = _ZERO3 if v0 is None else v0
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, r0_N=r0, v0_N=v0, t0=0.0, mu=mu)
    dt = total_t / n_steps
    state = reckoner.state
    for i in range(1, n_steps + 1):
        state = reckoner.step(ImuSample(t=i * dt, omega_B=np.asarray(omega_B), accel_B=_ZERO3))
    return state


def test_constant_rate_about_body_axis_matches_analytic_mrp():
    omega = 0.5  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = 1.0

    state = _run_constant_rate(omega * axis, total_t, n_steps=2000)

    theta = omega * total_t
    expected = np.tan(theta / 4.0) * axis
    np.testing.assert_allclose(state.sigma_BN, expected, atol=1e-6)


def test_zero_input_with_zero_mu_leaves_state_unchanged():
    sigma0 = np.array([0.1, -0.05, 0.2])
    r0 = np.array([1.0e6, 2.0e6, -3.0e6])
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, r0_N=r0, v0_N=_ZERO3, t0=0.0, mu=0.0)

    state = reckoner.step(ImuSample(t=1.0, omega_B=_ZERO3, accel_B=_ZERO3))

    np.testing.assert_allclose(state.sigma_BN, sigma0, atol=1e-12)
    np.testing.assert_allclose(state.r_N, r0, atol=1e-9)
    np.testing.assert_allclose(state.v_N, _ZERO3, atol=1e-12)
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


def test_zero_mu_constant_acceleration_zero_rate_gives_analytic_v_and_r():
    accel = np.array([0.3, -0.1, 0.05])
    total_t = 10.0
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=_ZERO3, v0_N=_ZERO3, t0=0.0, mu=0.0)

    state = reckoner.step(ImuSample(t=total_t, omega_B=_ZERO3, accel_B=accel))

    np.testing.assert_allclose(state.v_N, accel * total_t, atol=1e-9)
    np.testing.assert_allclose(state.r_N, 0.5 * accel * total_t**2, atol=1e-6)


def test_circular_orbit_zero_accelerometer_matches_analytic_two_body_position():
    mu = 3.986004418e14  # m^3/s^2, Earth
    radius = 6_871_000.0  # m, ~500 km LEO altitude
    v_circ = math.sqrt(mu / radius)
    n = math.sqrt(mu / radius**3)  # mean motion, rad/s
    period = 2.0 * math.pi / n

    r0 = np.array([radius, 0.0, 0.0])
    v0 = np.array([0.0, v_circ, 0.0])
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=r0, v0_N=v0, t0=0.0, mu=mu)

    dt = 1.0
    n_steps = round((period / 4.0) / dt)
    state = reckoner.state
    for i in range(1, n_steps + 1):
        state = reckoner.step(ImuSample(t=i * dt, omega_B=_ZERO3, accel_B=_ZERO3))

    theta = n * state.t
    expected_r = radius * np.array([math.cos(theta), math.sin(theta), 0.0])
    assert np.linalg.norm(state.r_N - expected_r) < 1.0


def test_kinematics_match_dcm_derivative_for_nonaligned_rate():
    # For sigma not parallel to omega, B(sigma)'s cross-product term is the only one that
    # can couple the axes; a lone-axis-aligned case (as above) cannot exercise its sign.
    # C_BN's time derivative obeys Cdot_BN = -[omega_B x] C_BN regardless of attitude
    # parameterization (Schaub & Junkins eq. 3.28); check the propagator against that
    # independent identity by finite difference.
    sigma0 = np.array([0.1, 0.0, 0.0])
    omega = np.array([0.0, 0.0, 0.3])
    reckoner = ImuDeadReckoner(sigma0_BN=sigma0, r0_N=_ZERO3, v0_N=_ZERO3, t0=0.0, mu=0.0)
    dt = 1e-5

    state = reckoner.step(ImuSample(t=dt, omega_B=omega, accel_B=_ZERO3))

    c0 = mrp.dcm_NB(sigma0).T
    c1 = mrp.dcm_NB(state.sigma_BN).T
    cdot_finite_difference = (c1 - c0) / dt

    skew_omega = np.array(
        [[0.0, -omega[2], omega[1]], [omega[2], 0.0, -omega[0]], [-omega[1], omega[0], 0.0]]
    )
    expected_cdot = -skew_omega @ c0

    np.testing.assert_allclose(cdot_finite_difference, expected_cdot, atol=1e-3)


def test_non_positive_dt_raises():
    reckoner = ImuDeadReckoner(sigma0_BN=_ZERO3, r0_N=_ZERO3, v0_N=_ZERO3, t0=5.0, mu=0.0)

    with pytest.raises(ValueError):
        reckoner.step(ImuSample(t=5.0, omega_B=_ZERO3, accel_B=_ZERO3))

    with pytest.raises(ValueError):
        reckoner.step(ImuSample(t=4.0, omega_B=_ZERO3, accel_B=_ZERO3))
