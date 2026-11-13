"""Reading a Monte Carlo run file, and looking truth up at a telemetry write's time."""

from collections.abc import Mapping
from pathlib import Path

import h5py
import numpy as np

_NANOSECONDS_PER_SECOND = 1e9


def read_run(path: str | Path) -> dict[str, np.ndarray]:
    """One run file, read with h5py.

    Args:
        path: the run file.

    Returns:
        Each dataset by its path: `t_s` (s, (N,)) and `truth/*` and `imu/*` ((N, 3), or (N, 4)
        for a quaternion such as `truth/q_BN`) at every dynamics step; `tlm/<instance>.<channel>`
        (one row per write, strings for an enum channel) and `tlm_t/<instance>.<channel>` (s, each
        write's flight software time); and each root attribute by its name, such as
        `draw_gyro_bias_P_rad_s` and `commands`, the ground's command log as JSON.
    """
    with h5py.File(path, "r") as f:
        run = {name: np.asarray(value) for name, value in f.attrs.items()}
        for group in f.values():
            for name, dataset in group.items() if isinstance(group, h5py.Group) else ():
                strings = h5py.check_string_dtype(dataset.dtype) is not None
                run[f"{group.name[1:]}/{name}"] = (dataset.asstr() if strings else dataset)[()]
        run["t_s"] = f["t_s"][()]
    return run


def at(run: Mapping[str, np.ndarray], dataset: str, t_s: np.ndarray) -> np.ndarray:
    """A dataset recorded at every dynamics step, at given recorded times.

    Args:
        run: one run, as `read_run` returns it.
        dataset: the dataset's path, such as `truth/q_BN`.
        t_s: (M,) s, times each of which is in `run["t_s"]`, to the nanosecond.

    Returns:
        (M, ...) the dataset's rows at `t_s`.

    Raises:
        KeyError: naming the first time `run["t_s"]` does not hold.
    """
    recorded = np.round(run["t_s"] * _NANOSECONDS_PER_SECOND).astype(np.int64)
    wanted = np.round(np.asarray(t_s) * _NANOSECONDS_PER_SECOND).astype(np.int64)
    rows = np.minimum(np.searchsorted(recorded, wanted), recorded.size - 1)
    missing = wanted[recorded[rows] != wanted]
    if missing.size:
        raise KeyError(f"{dataset} has no row at t = {missing[0] / _NANOSECONDS_PER_SECOND} s")
    return run[dataset][rows]
