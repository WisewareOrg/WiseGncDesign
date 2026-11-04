"""The dead reckoner's tests: smoke tests, its 1 Hz cadence, and the Monte Carlo case.

The smoke tests check flight conditions with closed forms on the algorithm alone. The Monte Carlo
case runs the dead reckoner at 1 Hz on WiseDynamics' IMU spacecraft in Leo500, hosted by
`gnc_cdh.basilisk`, the dynamics stepping at `--sim-fidelity`'s rate. Each case runs one dispersed
spacecraft, writes its run file, and holds its estimate within bounds derived from its own drawn
IMU biases.
"""

from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
from Basilisk.architecture import messaging
from scipy.spatial.transform import Rotation
from wise_dynamics.basilisk import ImuSpacecraft, Leo500

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner
from gnc_algorithms.mrp import dcm_NB
from gnc_analysis.error_bounds import read_run, violations
from gnc_cdh.basilisk import AlgorithmModule

IMU_DCM_PB = np.eye(3)
"""The flight software's mounting [PB] of the IMU: identity on this spacecraft."""

UNITS = {"sigma_BN": "MRP", "r_BN_N": "m", "v_BN_N": "m/s"}
"""The units of each output in the run file, by its name."""

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
    reckoner = ImuDeadReckoner(sigma0, r0, v0, t0=0.0, mu=mu, dcm_PB=IMU_DCM_PB)
    dt = total_t / n_steps
    for i in range(1, n_steps + 1):
        reckoner.step(t=i * dt, AngVelPlatform=AngVelPlatform, AccelPlatform=AccelPlatform)
    return reckoner


def test_a_constant_rate_about_one_axis_matches_the_analytic_mrp():
    """A 0.5 rad/s rate about body x for 1 s lands within 1e-6 of sigma = tan(theta/4) x."""
    omega = 0.5  # rad/s
    axis = np.array([1.0, 0.0, 0.0])
    total_t = 1.0

    state = _propagate(omega * axis, _ZERO3, total_t, n_steps=2000)

    expected = np.tan(omega * total_t / 4.0) * axis
    np.testing.assert_allclose(
        state.sigma_BN, expected, atol=1e-6, err_msg="constant-rate MRP is not tan(theta/4)"
    )


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


def test_the_kinematics_match_the_dcm_derivative_for_a_nonaligned_rate():
    """The MRP kinematics match the DCM derivative for a non-aligned rate.

    One 1e-5 s step at a 0.3 rad/s rate about z from sigma = (0.1, 0, 0) matches
    dC_BN/dt = -[omega x] C_BN within 1e-3 per entry.
    """
    sigma0 = np.array([0.1, 0.0, 0.0])
    omega = np.array([0.0, 0.0, 0.3])
    reckoner = ImuDeadReckoner(sigma0, _AWAY_FROM_ORIGIN, _ZERO3, t0=0.0, mu=0.0, dcm_PB=IMU_DCM_PB)
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


def estimate_fields(fsw: AlgorithmModule) -> dict[str, tuple[Any, str, str]]:
    """The estimate's run-file datasets, `est/<output name>`, one per output of the host module.

    Args:
        fsw: the host module.

    Returns:
        Each dataset path to the `(message, field, units)` it is recorded from.
    """
    return {f"est/{name}": (message, name, UNITS[name]) for name, message in fsw.outputs.items()}


def bound_inputs() -> dict[str, float]:
    """The bound's inputs, for this test and the Monte Carlo notebook alike.

    Returns:
        `gyro_noise_std_rad_s` (rad/s) and `accel_noise_std_m_s2` (m/s^2) from `ImuSpacecraft`,
        `step_s`, the flight software's step `AlgorithmModule.period_s` (s), and `mu`, Earth's
        gravitational parameter from `Leo500` (m^3/s^2).
    """
    return {
        "gyro_noise_std_rad_s": ImuSpacecraft.gyro_noise_std_rad_s,
        "accel_noise_std_m_s2": ImuSpacecraft.accel_noise_std_m_s2,
        "step_s": AlgorithmModule.period_s,
        "mu": Leo500.mu_m3_s2["earth"],
    }


def dead_reckoner(scenario: Leo500) -> AlgorithmModule:
    """The dead reckoner, built at t = 0 from a scenario's initial state, hosted on its vehicle.

    Args:
        scenario: the scenario whose vehicle and initial state the dead reckoner takes.

    Returns:
        The `AlgorithmModule` hosting it.
    """
    initial = scenario.initial_state()
    algorithm = ImuDeadReckoner(
        initial["sigma0_BN"],
        initial["r0_N"],
        initial["v0_N"],
        t0=0.0,
        mu=Leo500.mu_m3_s2["earth"],
        dcm_PB=IMU_DCM_PB,
    )
    return AlgorithmModule(algorithm, scenario.vehicle.readers())


def test_the_estimate_is_written_at_whole_seconds():
    """Run 3.5 s in Leo500, the estimate is last written at 3 s.

    The module runs at its 1 s `period_s`, not at the dynamics step.
    """
    scenario = Leo500()
    fsw = dead_reckoner(scenario)
    estimate = messaging.NavAttMsgReader()
    estimate.subscribeTo(fsw.output_messages["nav_att"])

    scenario.run(fsw, {}, duration_s=3.5)

    assert estimate.timeWritten() == 3_000_000_000
    assert fsw.algorithm.t == 3.0


def test_imu_dead_reckoning_case(
    sim_scenario: Leo500, sim_duration_s: float, sim_run_file: Callable[..., Path]
) -> None:
    """One Monte Carlo case holds every error within its bound.

    Args:
        sim_scenario: the case's dispersed scenario, from WiseDynamics' plugin.
        sim_duration_s: s, the case's simulated duration.
        sim_run_file: writes the case's run file and returns its path.
    """
    fsw = dead_reckoner(sim_scenario)
    datasets = sim_scenario.run(fsw, estimate_fields(fsw), duration_s=sim_duration_s)
    path = sim_run_file(datasets, {"versions_wise_gnc_design": version("wise-gnc-design")})

    assert violations(read_run(path), **bound_inputs()) == []
