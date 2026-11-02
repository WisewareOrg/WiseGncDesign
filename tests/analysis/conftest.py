"""Synthetic run files with a known injected error, written to the layout `gnc_analysis.runs`
reads."""

from collections.abc import Callable, Sequence
from pathlib import Path

import h5py
import numpy as np
import pytest

from gnc_analysis.runs import DATASETS

TRUTH_RATE_RAD_S = 0.1  # rad/s, about TRUTH_AXIS: past 180 deg within a 60 s run
TRUTH_AXIS = np.array([0.0, 0.6, 0.8])
ATTITUDE_ERROR_AXIS = np.array([1.0, 0.0, 0.0])
POSITION_ERROR_AXIS = np.array([0.0, 1.0, 0.0])


def _axis_angle_quaternion(axis: np.ndarray, angle_rad: np.ndarray) -> np.ndarray:
    """(N, 4) scalar-first unit quaternions of rotations by `angle_rad` about unit `axis`."""
    half = 0.5 * np.asarray(angle_rad)[:, None]
    return np.concatenate((np.cos(half), np.sin(half) * axis[None, :]), axis=1)


def _product(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Row-wise scalar-first product whose DCM is `C(p) @ C(q)`."""
    p0, pv, q0, qv = p[:, :1], p[:, 1:], q[:, :1], q[:, 1:]
    scalar = p0 * q0 - np.sum(pv * qv, axis=1, keepdims=True)
    return np.concatenate((scalar, p0 * qv + q0 * pv - np.cross(pv, qv)), axis=1)


def _mrp(q: np.ndarray) -> np.ndarray:
    q = np.where(q[:, :1] < 0.0, -q, q)
    return q[:, 1:] / (1.0 + q[:, :1])


def run_arrays(
    n_steps: int,
    dt: float,
    attitude_drift_rate_deg_s: float,
    position_drift_rate_m_s: float,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """One run's datasets. Truth tumbles about `TRUTH_AXIS`; the estimate's attitude error is a
    rotation about `ATTITUDE_ERROR_AXIS` whose angle grows at `attitude_drift_rate_deg_s`, and
    its position error grows along `POSITION_ERROR_AXIS` at `position_drift_rate_m_s` from a
    constant velocity error of that magnitude."""
    t_s = np.arange(n_steps) * dt
    q_truth = _axis_angle_quaternion(TRUTH_AXIS, TRUTH_RATE_RAD_S * t_s)
    error_rad = np.deg2rad(attitude_drift_rate_deg_s * t_s) + rng.normal(0.0, 1e-6, n_steps)
    q_error = _axis_angle_quaternion(ATTITUDE_ERROR_AXIS, error_rad)
    q_error_inverse = q_error * np.array([1.0, -1.0, -1.0, -1.0])
    # truth ⊖ est = error, i.e. C_truth C_est^T = C_error, so C_est = C_error^T C_truth.
    q_est = _product(q_error_inverse, q_truth)

    truth_r = np.zeros((n_steps, 3))
    truth_v = np.zeros((n_steps, 3))
    velocity_error = position_drift_rate_m_s * POSITION_ERROR_AXIS
    return {
        "t_s": t_s,
        "truth/sigma_BN": _mrp(q_truth),
        "truth/omega_BN_B": np.tile(TRUTH_RATE_RAD_S * TRUTH_AXIS, (n_steps, 1)),
        "truth/r_N": truth_r,
        "truth/v_N": truth_v,
        "est/sigma_BN": _mrp(q_est),
        "est/r_N": truth_r + t_s[:, None] * velocity_error[None, :],
        "est/v_N": truth_v + velocity_error[None, :],
        "imu/gyro_P": np.tile(TRUTH_RATE_RAD_S * TRUTH_AXIS, (n_steps, 1))
        + rng.normal(0.0, 1e-5, (n_steps, 3)),
        "imu/accel_P": rng.normal(0.0, 1e-6, (n_steps, 3)),
    }


def write_run_file(
    path: Path,
    case: int = 0,
    n_steps: int = 60,
    dt: float = 1.0,
    attitude_drift_rate_deg_s: float = 2.0,
    position_drift_rate_m_s: float = 0.5,
    seed: int = 0,
) -> Path:
    """Writes one run file at `path` with the injected drifts of `run_arrays`; returns `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng([seed, case])
    arrays = run_arrays(n_steps, dt, attitude_drift_rate_deg_s, position_drift_rate_m_s, rng)
    with h5py.File(path, "w") as f:
        f.attrs["case"] = case
        f.attrs["seed"] = seed
        f.attrs["producer"] = "tests/analysis"
        f.attrs["created_utc"] = "2026-10-31T00:00:00Z"
        f.attrs["versions_wise_gnc_design"] = "0.0.0"
        f.attrs["draw_gyro_bias"] = np.zeros(3)
        for name, data in arrays.items():
            f.create_dataset(name, data=data.astype(np.float64)).attrs["units"] = DATASETS[
                name
            ].units
    return path


@pytest.fixture
def run_file(tmp_path: Path) -> Callable[..., Path]:
    """`run_file(**kwargs)` writes `tmp_path/run_0000.h5` through `write_run_file`."""

    def make(**kwargs) -> Path:
        return write_run_file(tmp_path / f"run_{kwargs.get('case', 0):04d}.h5", **kwargs)

    return make


@pytest.fixture
def campaign_dir(tmp_path: Path) -> Callable[..., Path]:
    """`campaign_dir(attitude_drift_rates_deg_s, position_drift_rates_m_s, **kwargs)` writes one
    run file per pair of rates, cases 0 upward, into `tmp_path/campaign` and returns it."""

    def make(
        attitude_drift_rates_deg_s: Sequence[float] = (2.0,) * 5,
        position_drift_rates_m_s: Sequence[float] = (0.5,) * 5,
        **kwargs,
    ) -> Path:
        directory = tmp_path / "campaign"
        rates = zip(attitude_drift_rates_deg_s, position_drift_rates_m_s, strict=True)
        for case, (attitude_rate, position_rate) in enumerate(rates):
            write_run_file(
                directory / f"run_{case:04d}.h5",
                case=case,
                attitude_drift_rate_deg_s=attitude_rate,
                position_drift_rate_m_s=position_rate,
                **kwargs,
            )
        return directory

    return make
