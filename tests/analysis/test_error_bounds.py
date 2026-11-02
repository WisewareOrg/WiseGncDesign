"""`gnc_analysis.error_bounds` on runs built term by term: each term of each growth against its
hand-computed value, the gravity factors at an orbit where n t = sqrt(3), and the bound factor
and start-of-run limit at their edges."""

from pathlib import Path

import numpy as np
import pytest

from gnc_analysis.error_bounds import bound_ratios, error_growth, violations
from gnc_analysis.runs import Estimate, ImuReadings, Run, Truth

T_S = np.arange(0.0, 101.0, 10.0)  # s
R0_M = 7.0e6  # m, |r0|
# n t = sqrt(3) at t = 100 s: n = sqrt(3) / 100 rad/s, mu = n^2 |r0|^3.
MU_AT_SQRT3 = 3.0e-4 * R0_M**3
Y = np.array([0.0, 1.0, 0.0])
ATTITUDE, VELOCITY, POSITION = "attitude error [rad]", "velocity error [m/s]", "position error [m]"


def _run(b_g=(0.0, 0.0, 0.0), b_a=(0.0, 0.0, 0.0), omega_z=None, position_error=None) -> Run:
    """A run whose truth sits at |r0| on x and turns about z at `omega_z` (rad/s, per sample),
    with drawn biases `b_g`, `b_a`, and an estimate off truth by `position_error` (m) along y."""
    n = T_S.size
    zeros = np.zeros((n, 3))
    omega = zeros.copy()
    if omega_z is not None:
        omega[:, 2] = omega_z
    truth_r = np.tile([R0_M, 0.0, 0.0], (n, 1))
    est_r = truth_r if position_error is None else truth_r + position_error[:, None] * Y
    return Run(
        path=Path("synthetic.h5"),
        case=0,
        seed=0,
        draws={"gyro_bias_P": np.asarray(b_g), "accel_bias_P": np.asarray(b_a)},
        versions={},
        t_s=T_S,
        truth=Truth(sigma_BN=zeros, omega_BN_B=omega, r_N=truth_r, v_N=zeros),
        est=Estimate(sigma_BN=zeros, r_N=est_r, v_N=zeros),
        imu=ImuReadings(gyro_P=zeros, accel_P=zeros),
    )


def _growth(run: Run, name: str, sigma_g=0.0, sigma_a=0.0, step_s=1.0, mu=0.0) -> np.ndarray:
    return error_growth(run, sigma_g, sigma_a, step_s, mu)[name][1]


def test_attitude_bias_term_is_b_g_t():
    run = _run(b_g=(3e-4, 4e-4, 0.0))  # |b_g| = 5e-4 rad/s

    np.testing.assert_allclose(_growth(run, ATTITUDE), 5e-4 * T_S, rtol=1e-15)


def test_attitude_held_rate_term_is_half_omega_dot_dt_t():
    run = _run(omega_z=2e-3 * T_S)  # a ramp of 2e-3 rad/s^2

    np.testing.assert_allclose(_growth(run, ATTITUDE, step_s=0.5), 0.5 * 2e-3 * 0.5 * T_S)


def test_attitude_noise_term_is_three_sigma_root_t_dt():
    np.testing.assert_allclose(
        _growth(_run(), ATTITUDE, sigma_g=5e-5, step_s=0.5), 3.0 * 5e-5 * np.sqrt(T_S * 0.5)
    )


def test_translational_bias_terms_without_gravity_are_b_a_t_and_half_b_a_t_squared():
    run = _run(b_a=(0.0, 3e-4, 4e-4))  # |b_a| = 5e-4 m/s^2

    np.testing.assert_allclose(_growth(run, VELOCITY), 5e-4 * T_S, rtol=1e-15)
    np.testing.assert_allclose(_growth(run, POSITION), 0.5 * 5e-4 * T_S**2, rtol=1e-15)


def test_translational_noise_terms_without_gravity():
    run = _run()

    np.testing.assert_allclose(
        _growth(run, VELOCITY, sigma_a=5e-5, step_s=0.5), 3.0 * 5e-5 * np.sqrt(T_S * 0.5)
    )
    np.testing.assert_allclose(
        _growth(run, POSITION, sigma_a=5e-5, step_s=0.5),
        3.0 * 5e-5 * np.sqrt(0.5 / 3.0) * T_S**1.5,
    )


@pytest.mark.parametrize(
    ("terms", "kwargs"),
    [("bias", {"run": _run(b_a=(5e-4, 0.0, 0.0))}), ("noise", {"run": _run(), "sigma_a": 5e-5})],
)
@pytest.mark.parametrize(("name", "factor"), [(VELOCITY, 2.0), (POSITION, 1.5)])
def test_the_gravity_factor_at_n_t_sqrt3_is_two_for_velocity_and_one_and_a_half_for_position(
    terms, kwargs, name, factor
):
    noise = {key: value for key, value in kwargs.items() if key != "run"}

    with_gravity = _growth(kwargs["run"], name, mu=MU_AT_SQRT3, **noise)
    without_gravity = _growth(kwargs["run"], name, mu=0.0, **noise)

    assert with_gravity[-1] == pytest.approx(factor * without_gravity[-1], rel=1e-12)


@pytest.mark.parametrize(("multiple", "expected"), [(2.99, 0), (3.01, 1)])
def test_the_bound_factor_is_three(multiple, expected):
    growth = _growth(_run(b_a=(5e-4, 0.0, 0.0)), POSITION)
    run = _run(b_a=(5e-4, 0.0, 0.0), position_error=multiple * growth)

    found = violations(run, 0.0, 0.0, 1.0, 0.0)

    assert len(found) == expected
    assert all(POSITION in message for message in found)


@pytest.mark.parametrize(("start_error", "expected"), [(0.9e-9, 0), (1.1e-9, 1)])
def test_the_error_at_t0_is_held_under_1e_minus_9(start_error, expected):
    position_error = np.zeros(T_S.size)
    position_error[0] = start_error
    run = _run(b_a=(5e-4, 0.0, 0.0), position_error=position_error)

    found = violations(run, 0.0, 0.0, 1.0, 0.0)

    assert len(found) == expected
    assert all("at t = 0" in message for message in found)


def test_bound_ratios_leave_out_t0_and_are_finite():
    ratios = bound_ratios(_run(b_g=(1e-4, 0, 0), b_a=(1e-4, 0, 0)), 5e-5, 5e-5, 1.0, MU_AT_SQRT3)

    assert set(ratios) == {ATTITUDE, VELOCITY, POSITION}
    for name, ratio in ratios.items():
        assert ratio.shape == (T_S.size - 1,), name
        assert np.isfinite(ratio).all(), name
