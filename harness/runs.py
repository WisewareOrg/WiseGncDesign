"""Reading a Monte Carlo run file."""

from pathlib import Path

import h5py
import numpy as np


def read_run(path: str | Path) -> dict[str, np.ndarray]:
    """One run file, read with h5py.

    Args:
        path: the run file.

    Returns:
        Each dataset by its path, `t_s` (s, (N,)) and `truth/*`, `est/*` and `imu/*` ((N, 3), or
        (N, 4) for a quaternion such as `truth/q_BN`),
        and each root attribute by its name, such as `draw_gyro_bias_P_rad_s`.
    """
    with h5py.File(path, "r") as f:
        run = {name: np.asarray(value) for name, value in f.attrs.items()}
        for group in f.values():
            for name, dataset in group.items() if isinstance(group, h5py.Group) else ():
                run[f"{group.name[1:]}/{name}"] = dataset[()]
        run["t_s"] = f["t_s"][()]
    return run
