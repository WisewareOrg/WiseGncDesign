"""The IMU dead reckoner's smoke tests, and its gross check's.

Flight conditions with closed forms check the algorithm alone, with no simulator.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from wise_dynamics.basilisk import ImuSpacecraft

from gnc_algorithms.imu_dead_reckoning.gross_check import bound_inputs, violations
from gnc_algorithms.imu_dead_reckoning.imu_dead_reckoning import ImuDeadReckoner, _q_dot
from gnc_cdh.basilisk import AlgorithmModule
from harness.notebook import run_notebook

_IDENTITY = np.eye(3)
# The tests' IMU mounting [PB]: the platform frame is the body frame.
_ZERO3 = np.zeros(3)
# A position away from the origin for the attitude tests, which hold mu = 0 because gravity
# plays no part in attitude.
_AWAY_FROM_ORIGIN = np.array([7.0e6, 0.0, 0.0])
_Q_IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])


def _propagate(
    AngVelPlatform: np.ndarray,
    AccelPlatform: np.ndarray,
    total_t: float,
    n_steps: int,
    q0: np.ndarray = _Q_IDENTITY,
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
        q0: (4,) quaternion W X Y Z, the initial attitude of the body frame with respect to N.
        mu: m^3/s^2, the gravitational parameter.
        r0: (3,) m, the initial inertial position in N.
        v0: (3,) m/s, the initial inertial velocity in N.

    Returns:
        The stepped `ImuDeadReckoner`, holding `t`, `q_BN`, `r_BN_N` and `v_BN_N`.
    """
    reckoner = _commanded(q0, r0, v0, mu=mu)
    dt = total_t / n_steps
    for i in range(1, n_steps + 1):
        reckoner.step(t=i * dt, AngVelPlatform=AngVelPlatform, AccelPlatform=AccelPlatform)
    return reckoner


def _commanded(q0: np.ndarray, r0: np.ndarray, v0: np.ndarray, mu: float = 0.0) -> ImuDeadReckoner:
    """A dead reckoner, mounted at identity, given its state as of t = 0 by command.

    Args:
        q0: (4,) quaternion W X Y Z, the attitude of the body frame with respect to N.
        r0: (3,) m, the inertial position in N.
        v0: (3,) m/s, the inertial velocity in N.
        mu: m^3/s^2, the gravitational parameter.

    Returns:
        The `ImuDeadReckoner`, initialized.
    """
    reckoner = ImuDeadReckoner(mu=mu, dcm_PB=_IDENTITY)
    reckoner.initNavState(epoch=0.0, attitude=q0, position=r0, velocity=v0)
    return reckoner


def test_it_boots_idle_and_writes_only_navstate_until_commanded():
    """Booted, each step writes `navState` idle and nothing else, holding no state."""
    reckoner = ImuDeadReckoner(mu=0.0, dcm_PB=_IDENTITY)

    written = reckoner.step(t=1.0, AngVelPlatform=_ZERO3, AccelPlatform=_ZERO3)

    assert written == {"navState": "idle"}
    assert not hasattr(reckoner, "q_BN")


def test_the_command_writes_navstate_alone_and_the_next_step_propagates_from_its_epoch():
    """`initNavState` writes only `navState`; the step after it propagates from the epoch.

    At rest with mu = 0, a state at epoch 60 s with velocity v is at r0 + v (61 - 60) at t = 61 s.
    """
    reckoner = ImuDeadReckoner(mu=0.0, dcm_PB=_IDENTITY)
    velocity = np.array([1.0, 2.0, 3.0])

    commanded = reckoner.initNavState(
        epoch=60.0, attitude=_Q_IDENTITY, position=_AWAY_FROM_ORIGIN, velocity=velocity
    )
    stepped = reckoner.step(t=61.0, AngVelPlatform=_ZERO3, AccelPlatform=_ZERO3)

    assert commanded == {"navState": "initialized"}
    assert list(stepped) == ["navState", "bodyEciPos", "bodyEciVel", "bodyEciAttitude"]
    assert stepped["navState"] == "propagated"
    np.testing.assert_allclose(stepped["bodyEciPos"], _AWAY_FROM_ORIGIN + velocity, rtol=1e-15)
    np.testing.assert_array_equal(stepped["bodyEciVel"], velocity)
    np.testing.assert_array_equal(stepped["bodyEciAttitude"], _Q_IDENTITY)


# Past a rotation of $\pi$ the quaternion's $q_w$ would turn negative; the step keeps $q_w \ge 0$,
# and the attitude still matches the axis-angle rotation $R(\omega t\,\hat e)$ of a constant rate
# $\omega$ about $\hat e$, as SciPy computes it.
def test_a_rotation_past_180_degrees_keeps_w_nonnegative_on_the_axis_angle_attitude():
    """A rotation past 180 degrees ends with W >= 0, within 1e-5 rad of SciPy's rotation.

    A 1 rad/s rate about body x for 1.2 pi s, in 4000 steps.
    """
    omega = 1.0  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = np.pi * 1.2  # theta = 1.2 pi > pi

    state = _propagate(omega * axis, _ZERO3, total_t, n_steps=4000)

    assert state.q_BN[0] >= 0.0
    estimate = Rotation.from_quat(state.q_BN, scalar_first=True)
    assert (estimate * Rotation.from_rotvec(omega * total_t * axis).inv()).magnitude() <= 1e-5


# RK4 on $\dot q = \tfrac12 q \otimes (0, \omega)$ drifts $|q|$ off 1 at sixth order in the step's
# angle, so a coarse step shows whether the step normalizes; a fine one would hide it.
def test_a_coarse_step_keeps_q_unit():
    """Twenty 0.5 s steps at 1 rad/s leave |q| = 1 to 1e-15."""
    state = _propagate(np.array([0.0, 0.6, 0.8]), _ZERO3, total_t=10.0, n_steps=20)

    assert abs(np.linalg.norm(state.q_BN) - 1.0) <= 1e-15


def test_a_commanded_quaternion_with_w_negative_is_held_with_w_nonnegative():
    """Commanded with -q, W < 0, the reckoner holds q."""
    q = Rotation.from_rotvec([0.3, -0.2, 0.1]).as_quat(scalar_first=True)

    reckoner = _commanded(-q, _AWAY_FROM_ORIGIN, _ZERO3)

    np.testing.assert_array_equal(reckoner.q_BN, q)


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


# The quaternion kinematics agree with the direction cosine matrix derivative identity
#
# $$\dot C_{BN} = -[\omega\times]\,C_{BN}$$
def test_the_kinematics_match_the_dcm_derivative_for_a_nonaligned_rate():
    """The quaternion kinematics match the DCM derivative for a non-aligned rate.

    One 1e-5 s step at a 0.3 rad/s rate about z from a rotation of 0.4 rad about x matches
    dC_BN/dt = -[omega x] C_BN within 1e-3 per entry.
    """
    q0 = Rotation.from_rotvec([0.4, 0.0, 0.0]).as_quat(scalar_first=True)
    omega = np.array([0.0, 0.0, 0.3])
    reckoner = _commanded(q0, _AWAY_FROM_ORIGIN, _ZERO3)
    dt = 1e-5

    state = reckoner.step(t=dt, AngVelPlatform=omega, AccelPlatform=_ZERO3)

    c0 = Rotation.from_quat(q0, scalar_first=True).as_matrix().T
    c1 = Rotation.from_quat(state["bodyEciAttitude"], scalar_first=True).as_matrix().T
    np.testing.assert_allclose(
        (c1 - c0) / dt,
        -np.cross(omega[:, None], c0, axis=0),
        atol=1e-3,
        err_msg="quaternion kinematics differ from the DCM derivative identity",
    )


@pytest.mark.parametrize("dt", [1e-3, 1e-4])
def test_q_dot_steps_the_attitude_as_scipy_rotates_it(dt: float):
    """A step q + dq/dt dt agrees with q rotated by omega dt in B, to first order in dt.

    Args:
        dt: s, the step, whose square bounds the agreement.
    """
    omega = np.array([0.3, -0.2, 0.5])
    for q in Rotation.random(200, random_state=5).as_quat(scalar_first=True):
        rotated = Rotation.from_quat(q, scalar_first=True) * Rotation.from_rotvec(omega * dt)
        expected = rotated.as_quat(scalar_first=True, canonical=False)
        expected *= np.sign(expected @ q)
        np.testing.assert_allclose(q + _q_dot(q, omega) * dt, expected, rtol=0, atol=dt**2)


def _run(t_s: np.ndarray) -> dict[str, object]:
    """A run file's contents with every error zero, every bias and rate zero, one write a tick.

    Args:
        t_s: (N,) s, the dynamics steps, each also an estimate write.

    Returns:
        The run, as `read_run` returns it.
    """
    n = len(t_s)
    identity = np.tile([1.0, 0.0, 0.0, 0.0], (n, 1))
    r_N = np.tile([7.0e6, 0.0, 0.0], (n, 1))
    commands = [
        {"name": "nav.initNavState", "args": {"epoch": 0.0}, "response": "OK", "context": 1}
    ]
    return {
        "t_s": t_s,
        "commands": np.asarray(json.dumps(commands)),
        "truth/q_BN": identity,
        "truth/omega_BN_B": np.zeros((n, 3)),
        "truth/v_N": np.zeros((n, 3)),
        "truth/r_N": r_N,
        "tlm/nav.bodyEciAttitude": identity.copy(),
        "tlm/nav.bodyEciVel": np.zeros((n, 3)),
        "tlm/nav.bodyEciPos": r_N.copy(),
        **{f"tlm_t/nav.bodyEci{name}": t_s for name in ("Attitude", "Vel", "Pos")},
        "draw_gyro_bias_P_rad_s": np.zeros(3),
        "draw_accel_bias_P_m_s2": np.zeros(3),
    }


def test_a_nan_error_is_a_violation():
    """A diverged estimate, whose error is NaN, fails the gross check instead of passing it."""
    run = _run(np.array([1.0, 2.0, 3.0]))
    run["tlm/nav.bodyEciVel"][2, 0] = np.nan

    found = violations(run, **bound_inputs())

    assert [message.split()[0] for message in found] == ["velocity"]


def test_the_bound_takes_each_sample_s_noise_from_the_density_and_the_step() -> None:
    """The per-sample noise is the density over the square root of the flight software's step."""
    assert bound_inputs()["gyro_noise_std_rad_s"] == 5e-5
    assert bound_inputs()["accel_noise_std_m_s2"] == 5e-5


def test_a_longer_step_lowers_each_sample_s_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    """At a 4 s step each sample carries half the density, as the IMU sampling every 4 s does.

    Args:
        monkeypatch: replaces the flight software's step for this test.
    """
    monkeypatch.setattr(AlgorithmModule, "period_s", 4.0)
    inputs = bound_inputs()
    assert inputs["step_s"] == 4.0
    assert inputs["gyro_noise_std_rad_s"] == ImuSpacecraft.gyro_noise_density_rad_s_rthz / 2
    assert inputs["accel_noise_std_m_s2"] == ImuSpacecraft.accel_noise_density_m_s2_rthz / 2


@pytest.mark.xdist_group("notebooks")
def test_the_notebook_runs_end_to_end() -> None:
    """Every cell of the algorithm notebook runs, the notebook-only cells included."""
    run_notebook(Path(__file__).with_name("imu_dead_reckoning.py"))


@pytest.mark.xdist_group("notebooks")
def test_the_parity_notebook_runs_end_to_end() -> None:
    """Every cell of the parity notebook runs, so the two builds agree case by case."""
    pytest.importorskip("gnc_cdh.fprime._wise_fsw", reason="the F´ build is absent; run `just fsw`")
    run_notebook(Path(__file__).with_name("parity.py"))
