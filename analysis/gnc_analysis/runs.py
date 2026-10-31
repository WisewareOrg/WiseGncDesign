"""What a run file must contain, and the loader that is the only statement of it.

See this repository's README, "What a run file must contain". This loader is the sole
authority, raising RunDataError naming the file and the dataset, attribute or unit at fault.
"""

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

# Dataset path within a run file -> its expected `units` attribute.
DATASETS = {
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


class RunDataError(Exception):
    """Signals a mismatch between a run file's content and what the loader requires."""


@dataclass(frozen=True)
class Run:
    path: Path
    case: int
    seed: int
    draws: dict[str, np.ndarray]
    versions: dict[str, str]
    t_s: np.ndarray
    truth_sigma_BN: np.ndarray
    truth_omega_BN_B: np.ndarray
    truth_r_N: np.ndarray
    truth_v_N: np.ndarray
    est_sigma_BN: np.ndarray
    est_r_N: np.ndarray
    est_v_N: np.ndarray
    imu_gyro_P: np.ndarray
    imu_accel_P: np.ndarray


def _read_dataset(f: h5py.File, path: Path, rel_path: str, expected_units: str) -> np.ndarray:
    if rel_path not in f:
        raise RunDataError(f"{path}: missing dataset '{rel_path}'")

    dataset = f[rel_path]
    data = dataset[()]

    actual_units = dataset.attrs.get("units")
    if actual_units != expected_units:
        raise RunDataError(
            f"{path}: dataset '{rel_path}' has units {actual_units!r}, expected {expected_units!r}"
        )

    if np.isnan(data).any():
        raise RunDataError(f"{path}: dataset '{rel_path}' contains NaN")

    return data


def load_run(path: str | Path) -> Run:
    """Load one run_<NNNN>.h5. Reads each dataset in DATASETS by name, checks its `units`
    attribute, rejects NaN, and requires t_s strictly increasing from 0; requires the root attrs
    `case` and `seed`. `draw_*` and `versions_*` attrs are read best-effort. Extra datasets and
    attributes are ignored. Raises RunDataError naming the file and the dataset, attribute or
    unit at fault."""
    path = Path(path)
    if not path.is_file():
        raise RunDataError(f"{path}: file does not exist")

    try:
        handle = h5py.File(path, "r")
    except OSError as exc:
        raise RunDataError(f"{path}: could not be opened as HDF5 ({exc})") from exc

    with handle as f:
        values = {
            rel_path: _read_dataset(f, path, rel_path, units)
            for rel_path, units in DATASETS.items()
        }

        t_s = values["t_s"]
        not_increasing_from_zero = (
            t_s.size == 0 or t_s[0] != 0 or (t_s.size > 1 and (t_s[1:] <= t_s[:-1]).any())
        )
        if not_increasing_from_zero:
            raise RunDataError(f"{path}: t_s is not strictly increasing from 0")

        if "case" not in f.attrs:
            raise RunDataError(f"{path}: missing root attr 'case'")
        if "seed" not in f.attrs:
            raise RunDataError(f"{path}: missing root attr 'seed'")
        case = int(f.attrs["case"])
        seed = int(f.attrs["seed"])
        draws = {
            name.removeprefix("draw_"): np.asarray(value)
            for name, value in f.attrs.items()
            if name.startswith("draw_")
        }
        versions = {
            name: str(value) for name, value in f.attrs.items() if name.startswith("versions_")
        }

        return Run(
            path=path,
            case=case,
            seed=seed,
            draws=draws,
            versions=versions,
            t_s=t_s,
            truth_sigma_BN=values["truth/sigma_BN"],
            truth_omega_BN_B=values["truth/omega_BN_B"],
            truth_r_N=values["truth/r_N"],
            truth_v_N=values["truth/v_N"],
            est_sigma_BN=values["est/sigma_BN"],
            est_r_N=values["est/r_N"],
            est_v_N=values["est/v_N"],
            imu_gyro_P=values["imu/gyro_P"],
            imu_accel_P=values["imu/accel_P"],
        )


def load_campaign(directory: str | Path) -> list[Run]:
    """Load every run_*.h5 in directory, sorted by filename, via load_run. Raises RunDataError
    naming the offending file if any run's t_s differs from the others."""
    directory = Path(directory)
    paths = sorted(directory.glob("run_*.h5"))
    if not paths:
        raise RunDataError(f"{directory}: no run_*.h5 files found")

    runs = [load_run(p) for p in paths]

    reference = runs[0]
    for run in runs[1:]:
        same_shape = run.t_s.shape == reference.t_s.shape
        if not same_shape or not np.allclose(run.t_s, reference.t_s, rtol=0, atol=1e-9):
            raise RunDataError(f"{run.path}: t_s differs from {reference.path}'s t_s")

    return runs
