"""The IMU dead reckoner's smoke tests, and its gross check's.

Flight conditions with closed forms check the algorithm alone, with no simulator.
"""

import numpy as np
from scipy.spatial.transform import Rotation

from gnc_algorithms.imu_dead_reckoning.gross_check import bound_inputs, violations
from gnc_algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner
from gnc_algorithms.mrp import dcm_NB

_IDENTITY = np.eye(3)
# The tests' IMU mounting [PB]: the platform frame is the body frame.
_ZERO3 = np.zeros(3)
# A position away from the origin for the attitude tests, which hold mu = 0 because gravity
# plays no part in attitude.
_AWAY_FROM_ORIGIN = np.array([7.0e6, 0.0, 0.0])


def _propagate(
    AngVelPlatform: np.ndarray,
    AccelPlatform: np.ndarray,
    total_t: float,
    n_steps: int,
    sigma0: np.ndarray = _ZERO3,
    mu: float = 0.0,
    r0: np.ndarray = _AWAY_FROM_ORIGIN,
    v0: np.ndarray = _ZERO3,
) -> ImuDeadReckoner:
    """A dead reckoner, mounted at identity, stepped `n_steps` equal steps to `total_t`.

    Args:
        AngVelPlatform: (3,) rad/s, the gyro reading held across every step, in the IMU
            platform frame.
        AccelPlatform: (3,) m/s^2, the accelerometer reading held across every step, in that
            frame.
        total_t: s, the time it is stepped to from t = 0.
        n_steps: the number of equal steps.
        sigma0: (3,) MRP, the initial attitude of the body frame with respect to N.
        mu: m^3/s^2, the gravitational parameter.
        r0: (3,) m, the initial inertial position in N.
        v0: (3,) m/s, the initial inertial velocity in N.

    Returns:
        The stepped `ImuDeadReckoner`, holding `t`, `sigma_BN`, `r_BN_N` and `v_BN_N`.
    """
    reckoner = ImuDeadReckoner(sigma0, r0, v0, t0=0.0, mu=mu, dcm_PB=_IDENTITY)
    dt = total_t / n_steps
    for i in range(1, n_steps + 1):
        reckoner.step(t=i * dt, AngVelPlatform=AngVelPlatform, AccelPlatform=AccelPlatform)
    return reckoner


# Past a rotation of $\pi$ the shadow switch keeps $|\sigma| \le 1$, and the attitude still
# matches the axis-angle rotation $C_{NB}(\sigma) = R(\omega t\,\hat e)$ of a constant rate
# $\omega$ about $\hat e$, as SciPy computes it.
def test_a_rotation_past_180_degrees_switches_to_the_shadow_set():
    """A rotation past 180 degrees switches to the shadow set.

    A 1 rad/s rate about body x for 1.2 pi s keeps |sigma| <= 1, and its DCM matches SciPy's for
    that rotation within 1e-5.
    """
    omega = 1.0  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = np.pi * 1.2  # theta = 1.2 pi > pi

    state = _propagate(omega * axis, _ZERO3, total_t, n_steps=4000)

    assert np.linalg.norm(state.sigma_BN) <= 1.0, "no switch to the shadow set"
    np.testing.assert_allclose(
        dcm_NB(state.sigma_BN).T,
        Rotation.from_rotvec(omega * total_t * axis).as_matrix().T,
        atol=1e-5,
        err_msg="shadow-set DCM differs from the axis-angle DCM",
    )


# With gravity alone ($a_B = 0$), a circular orbit of radius $r_0$ has the mean motion
# $n = \sqrt{\mu / r_0^3}$ and the position
#
# $$r(t) = r_0\,(\cos nt,\ \sin nt,\ 0)$$
def test_gravity_alone_keeps_a_quarter_circular_orbit_on_the_analytic_position():
    """Gravity alone keeps a quarter circular orbit on its analytic position.

    At 1 s steps over a quarter of a 500 km circular orbit, the position lands within 1 m of the
    analytic one in N.
    """
    mu = 3.986004418e14  # m^3/s^2, Earth
    radius = 6_871_000.0  # m, about 500 km altitude
    n = np.sqrt(mu / radius**3)  # rad/s, mean motion
    n_steps = round((2.0 * np.pi / n / 4.0) / 1.0)

    state = _propagate(
        _ZERO3,
        _ZERO3,
        total_t=float(n_steps),
        n_steps=n_steps,
        mu=mu,
        r0=np.array([radius, 0.0, 0.0]),
        v0=np.array([0.0, np.sqrt(mu / radius), 0.0]),
    )

    theta = n * state.t
    expected_r = radius * np.array([np.cos(theta), np.sin(theta), 0.0])
    np.testing.assert_allclose(
        state.r_BN_N, expected_r, atol=1.0, err_msg="quarter-orbit position error exceeds 1 m"
    )


# The MRP kinematics agree with the direction cosine matrix derivative identity
#
# $$\dot C_{BN} = -[\omega\times]\,C_{BN}$$
def test_the_kinematics_match_the_dcm_derivative_for_a_nonaligned_rate():
    """The MRP kinematics match the DCM derivative for a non-aligned rate.

    One 1e-5 s step at a 0.3 rad/s rate about z from sigma = (0.1, 0, 0) matches
    dC_BN/dt = -[omega x] C_BN within 1e-3 per entry.
    """
    sigma0 = np.array([0.1, 0.0, 0.0])
    omega = np.array([0.0, 0.0, 0.3])
    reckoner = ImuDeadReckoner(sigma0, _AWAY_FROM_ORIGIN, _ZERO3, t0=0.0, mu=0.0, dcm_PB=_IDENTITY)
    dt = 1e-5

    state = reckoner.step(t=dt, AngVelPlatform=omega, AccelPlatform=_ZERO3)

    c0 = dcm_NB(sigma0).T
    c1 = dcm_NB(state["sigma_BN"]).T
    np.testing.assert_allclose(
        (c1 - c0) / dt,
        -np.cross(omega[:, None], c0, axis=0),
        atol=1e-3,
        err_msg="MRP kinematics differ from the DCM derivative identity",
    )


def test_a_nan_error_is_a_violation():
    """A diverged estimate, whose error is NaN, fails the gross check instead of passing it."""
    zeros = np.zeros((3, 3))
    r_N = np.tile([7.0e6, 0.0, 0.0], (3, 1))
    v_est_N = zeros.copy()
    v_est_N[2, 0] = np.nan
    run = {
        "t_s": np.array([0.0, 1.0, 2.0]),
        "truth/sigma_BN": zeros,
        "est/sigma_BN": zeros,
        "truth/omega_BN_B": zeros,
        "truth/v_N": zeros,
        "est/v_BN_N": v_est_N,
        "truth/r_N": r_N,
        "est/r_BN_N": r_N,
        "draw_gyro_bias_P_rad_s": np.zeros(3),
        "draw_accel_bias_P_m_s2": np.zeros(3),
    }

    found = violations(run, **bound_inputs())

    assert [message.split()[0] for message in found] == ["velocity"]
