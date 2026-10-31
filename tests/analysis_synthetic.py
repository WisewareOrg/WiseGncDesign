"""Synthetic run files, used by both the loader tests and the analysis test."""

from pathlib import Path

import h5py
import numpy as np

TRUTH_OMEGA = np.array([0.017, 0.017, 0.017])  # ~1 deg/s per axis
ATTITUDE_ERROR_AXIS = np.array([1.0, 0.0, 0.0])
POSITION_ERROR_AXIS = np.array([0.0, 1.0, 0.0])

UNITS = {
    "t_s": "s",
    "truth/sigma_BN": "MRP",
    "truth/omega_BN_B": "rad/s",
    "truth/r_N": "m",
    "truth/v_N": "m/s",
    "est/sigma_BN": "MRP",
    "est/r_N": "m",
    "est/v_N": "m/s",
    "imu/gyro_P": "rad/s",
    "imu/accel_P": "m/s^2",
}


def _run_arrays(
    n_steps: int,
    dt: float,
    attitude_drift_rate_deg_s: float,
    position_drift_rate_m_s: float,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """One run's datasets. Truth is held at rest at the origin with the identity attitude; the
    estimate drifts away from it such that the attitude error angle grows at
    attitude_drift_rate_deg_s (deg/s) and the position error grows linearly at
    position_drift_rate_m_s (m/s) — a constant velocity error of that magnitude."""
    t_s = np.arange(n_steps) * dt

    theta_rad = np.deg2rad(attitude_drift_rate_deg_s * t_s)
    mrp_mag = np.tan(theta_rad / 4.0) + rng.normal(0, 1e-5, size=n_steps)
    est_sigma_bn = mrp_mag[:, None] * ATTITUDE_ERROR_AXIS[None, :]

    truth_sigma_bn = np.zeros((n_steps, 3))
    truth_omega_bn_b = np.tile(TRUTH_OMEGA, (n_steps, 1))
    truth_r_n = np.zeros((n_steps, 3))
    truth_v_n = np.zeros((n_steps, 3))

    position_error_mag = position_drift_rate_m_s * t_s
    est_r_n = truth_r_n + position_error_mag[:, None] * POSITION_ERROR_AXIS[None, :]
    velocity_error = position_drift_rate_m_s * POSITION_ERROR_AXIS
    est_v_n = truth_v_n + np.tile(velocity_error, (n_steps, 1))

    gyro_p = truth_omega_bn_b + rng.normal(0, 1e-5, size=(n_steps, 3))
    accel_p = rng.normal(0, 1e-6, size=(n_steps, 3))

    return {
        "t_s": t_s,
        "truth/sigma_BN": truth_sigma_bn,
        "truth/omega_BN_B": truth_omega_bn_b,
        "truth/r_N": truth_r_n,
        "truth/v_N": truth_v_n,
        "est/sigma_BN": est_sigma_bn,
        "est/r_N": est_r_n,
        "est/v_N": est_v_n,
        "imu/gyro_P": gyro_p,
        "imu/accel_P": accel_p,
    }


def build_run(
    path: Path,
    case: int = 0,
    n_steps: int = 60,
    dt: float = 1.0,
    attitude_drift_rate_deg_s: float = 2.0,
    position_drift_rate_m_s: float = 0.5,
    seed: int = 0,
    producer: str = "synthetic-test",
) -> Path:
    """Write a single run_<NNNN>.h5 at path, with attitude error growing at
    attitude_drift_rate_deg_s and position error growing linearly at position_drift_rate_m_s.
    Returns path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    arrays = _run_arrays(n_steps, dt, attitude_drift_rate_deg_s, position_drift_rate_m_s, rng)

    with h5py.File(path, "w") as f:
        f.attrs["producer"] = producer
        f.attrs["created_utc"] = "2026-10-31T00:00:00Z"
        f.attrs["case"] = case
        f.attrs["seed"] = seed
        f.attrs["versions_bsk"] = "synthetic-test"
        f.attrs["versions_gnc_algorithms"] = "synthetic-test"
        f.attrs["versions_wise_dynamics"] = "synthetic-test"
        f.attrs["draw_sigma0"] = np.zeros(3)
        f.attrs["draw_omega0"] = TRUTH_OMEGA

        for rel_path, data in arrays.items():
            dataset = f.create_dataset(rel_path, data=data.astype(np.float64))
            dataset.attrs["units"] = UNITS[rel_path]

    return path


def build_campaign(
    directory: Path,
    n_runs: int = 5,
    n_steps: int = 60,
    dt: float = 1.0,
    attitude_drift_rate_deg_s: float = 2.0,
    position_drift_rate_m_s: float = 0.5,
    seed: int = 0,
    producer: str = "synthetic-test",
) -> Path:
    """Write n_runs run_<NNNN>.h5 files into directory, each via build_run with a distinct case
    and seed. Returns directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    for i in range(n_runs):
        build_run(
            directory / f"run_{i:04d}.h5",
            case=i,
            n_steps=n_steps,
            dt=dt,
            attitude_drift_rate_deg_s=attitude_drift_rate_deg_s,
            position_drift_rate_m_s=position_drift_rate_m_s,
            seed=seed + i,
            producer=producer,
        )

    return directory
