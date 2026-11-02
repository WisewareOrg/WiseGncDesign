"""Loads recorded runs: one HDF5 file per run, a campaign being a directory of them.

This loader is the single statement of what a run file must contain; `analysis/README.md`
("What a run file must contain") renders the same table for readers. Every rejection raises
`RunDataError` naming the file and the dataset, attribute or rule at fault.
"""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, NamedTuple

import h5py
import numpy as np

__all__ = [
    "DATASETS",
    "Dataset",
    "Estimate",
    "ImuReadings",
    "Run",
    "RunDataError",
    "Truth",
    "load_campaign",
    "load_run",
]


class RunDataError(Exception):
    """A run file, or a campaign directory, differs from what `load_run` and `load_campaign`
    read. The message names the file and the dataset, attribute or rule at fault."""


class Dataset(NamedTuple):
    """What one dataset must be: float64, carrying a string attr `units` equal to `units`, of
    shape `(N,)` when `width` is `None` and `(N, width)` otherwise, `N` being `len(t_s)`."""

    units: str
    width: int | None


def _channel(units: str, width: int | None = 3) -> Any:
    return field(metadata={"units": units, "width": width})


@dataclass(frozen=True)
class Truth:
    """Plant truth, one row per sample of `Run.t_s`. Read from group `truth/`.

    Attributes:
        sigma_BN: (N, 3) MRP of the body frame B with respect to the inertial frame N.
        omega_BN_B: (N, 3) rad/s, angular rate of B with respect to N, in B.
        r_N: (N, 3) m, inertial position.
        v_N: (N, 3) m/s, inertial velocity.
    """

    sigma_BN: np.ndarray = _channel("MRP")
    omega_BN_B: np.ndarray = _channel("rad/s")
    r_N: np.ndarray = _channel("m")
    v_N: np.ndarray = _channel("m/s")


@dataclass(frozen=True)
class Estimate:
    """The flight software's estimate, one row per sample of `Run.t_s`. Read from group `est/`.

    Attributes:
        sigma_BN: (N, 3) MRP of B with respect to N.
        r_N: (N, 3) m, inertial position.
        v_N: (N, 3) m/s, inertial velocity.
    """

    sigma_BN: np.ndarray = _channel("MRP")
    r_N: np.ndarray = _channel("m")
    v_N: np.ndarray = _channel("m/s")


@dataclass(frozen=True)
class ImuReadings:
    """The IMU's own output, in its sensor (platform) frame P, one row per sample of
    `Run.t_s`. Read from group `imu/`.

    Attributes:
        gyro_P: (N, 3) rad/s, angular rate in P.
        accel_P: (N, 3) m/s^2, non-gravitational acceleration in P.
    """

    gyro_P: np.ndarray = _channel("rad/s")
    accel_P: np.ndarray = _channel("m/s^2")


_GROUPS: dict[str, type] = {"truth": Truth, "est": Estimate, "imu": ImuReadings}

DATASETS: Mapping[str, Dataset] = MappingProxyType(
    {
        "t_s": Dataset("s", None),
        **{
            f"{group}/{f.name}": Dataset(f.metadata["units"], f.metadata["width"])
            for group, cls in _GROUPS.items()
            for f in dataclasses.fields(cls)
        },
    }
)
"""Every dataset a run file must contain, by its path in the file."""


@dataclass(frozen=True)
class Run:
    """One loaded run.

    Attributes:
        path: the file it was read from.
        case: root attr `case`, the run's index in its campaign.
        seed: root attr `seed`, the campaign seed it was drawn from.
        draws: every root attr `draw_<name>`, keyed by `<name>`.
        versions: every root attr `versions_<name>`, keyed by `<name>`.
        t_s: (N,) s, sample times, strictly increasing from 0.
        truth: plant truth at `t_s`.
        est: the flight software's estimate at `t_s`.
        imu: the IMU's output at `t_s`.
    """

    path: Path
    case: int
    seed: int
    draws: Mapping[str, np.ndarray]
    versions: Mapping[str, str]
    t_s: np.ndarray
    truth: Truth
    est: Estimate
    imu: ImuReadings


def _read_dataset(f: h5py.File, path: Path, name: str, spec: Dataset, rows: int | None) -> Any:
    if name not in f or not isinstance(f[name], h5py.Dataset):
        raise RunDataError(f"{path}: missing dataset '{name}'")
    dataset = f[name]

    units = dataset.attrs.get("units")
    if isinstance(units, bytes):
        units = units.decode()
    if units != spec.units:
        raise RunDataError(f"{path}: dataset '{name}' has units {units!r}, expected {spec.units!r}")
    if dataset.dtype != np.float64:
        raise RunDataError(f"{path}: dataset '{name}' has dtype {dataset.dtype}, expected float64")

    expected_ndim = 1 if spec.width is None else 2
    if dataset.ndim != expected_ndim or (spec.width is not None and dataset.shape[1] != spec.width):
        expected = "(N,)" if spec.width is None else f"(N, {spec.width})"
        raise RunDataError(
            f"{path}: dataset '{name}' has shape {dataset.shape}, expected {expected}"
        )
    if rows is not None and dataset.shape[0] != rows:
        raise RunDataError(
            f"{path}: dataset '{name}' has {dataset.shape[0]} rows, expected {rows} (len(t_s))"
        )

    data = dataset[()]
    if not np.isfinite(data).all():
        raise RunDataError(f"{path}: dataset '{name}' contains NaN or inf")
    return data


def _integral_attr(f: h5py.File, path: Path, name: str) -> int:
    if name not in f.attrs:
        raise RunDataError(f"{path}: missing root attr '{name}'")
    value = np.asarray(f.attrs[name])
    if value.shape != () or not np.issubdtype(value.dtype, np.integer):
        raise RunDataError(f"{path}: root attr '{name}' is {value!r}, expected an integer")
    return int(value)


def load_run(path: str | Path) -> Run:
    """Loads one run file.

    Reads every dataset in `DATASETS` by name and requires its `units`, its float64 dtype, its
    shape, `len(t_s)` rows and finite values; requires `t_s` to start at 0 and increase strictly;
    requires integer root attrs `case` and `seed`. Collects `draw_*` and `versions_*` root attrs.
    Ignores every other dataset and attr.

    Raises:
        RunDataError: naming the file and the dataset, attr or rule at fault.
    """
    path = Path(path)
    if not path.is_file():
        raise RunDataError(f"{path}: file does not exist")
    try:
        handle = h5py.File(path, "r")
    except OSError as exc:
        raise RunDataError(f"{path}: could not be opened as HDF5 ({exc})") from exc

    with handle as f:
        t_s = _read_dataset(f, path, "t_s", DATASETS["t_s"], rows=None)
        if t_s.size == 0 or t_s[0] != 0.0:
            raise RunDataError(f"{path}: t_s does not start at 0")
        if np.any(np.diff(t_s) <= 0.0):
            raise RunDataError(f"{path}: t_s is not strictly increasing")

        groups = {
            group: cls(
                **{
                    f_.name: _read_dataset(
                        f, path, f"{group}/{f_.name}", DATASETS[f"{group}/{f_.name}"], t_s.size
                    )
                    for f_ in dataclasses.fields(cls)
                }
            )
            for group, cls in _GROUPS.items()
        }

        case = _integral_attr(f, path, "case")
        seed = _integral_attr(f, path, "seed")
        draws = {
            name.removeprefix("draw_"): np.asarray(value)
            for name, value in f.attrs.items()
            if name.startswith("draw_")
        }
        versions = {
            name.removeprefix("versions_"): str(value)
            for name, value in f.attrs.items()
            if name.startswith("versions_")
        }

    return Run(
        path=path,
        case=case,
        seed=seed,
        draws=MappingProxyType(draws),
        versions=MappingProxyType(versions),
        t_s=t_s,
        **groups,
    )


def load_campaign(directory: str | Path) -> list[Run]:
    """Loads every `run_*.h5` in `directory`, sorted by file name, through `load_run`, and
    requires every run to share the first run's `t_s` (equal within 1e-9 s).

    Raises:
        RunDataError: when the directory holds no run file, when any run fails `load_run`, or
            naming the first run whose `t_s` differs.
    """
    directory = Path(directory)
    paths = sorted(directory.glob("run_*.h5"))
    if not paths:
        raise RunDataError(f"{directory}: no run_*.h5 files found")

    runs = [load_run(p) for p in paths]
    reference = runs[0]
    for run in runs[1:]:
        same = run.t_s.shape == reference.t_s.shape and np.allclose(
            run.t_s, reference.t_s, rtol=0.0, atol=1e-9
        )
        if not same:
            raise RunDataError(f"{run.path}: t_s differs from {reference.path}'s t_s")
    return runs
