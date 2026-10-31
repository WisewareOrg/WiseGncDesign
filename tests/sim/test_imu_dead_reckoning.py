"""One IMU on a tumbling spacecraft: `gnc_cdh.basilisk`'s `imu_dead_reckoning` flight software,
built on WiseDynamics' plant, writes one run file per case via WiseDynamics' own writer, read
back by this repository's own analysis loader."""

import numpy as np
from Basilisk.utilities import macros
from gnc_analysis.runs import load_run
from sim.basilisk.run import run_case

from gnc_cdh.basilisk import make_fsw

FSW_NAME = "imu_dead_reckoning"

# Contract v0 (README's "What a run file must contain"): dataset name -> (recorder, field,
# units). "truth" and "imu" are WiseDynamics' own plant recorders; "nav_att"/"nav_trans" are the
# flight software's own output roles (see gnc_cdh.bindings.BINDINGS["imu_dead_reckoning"]).
_EXPORT: dict[str, tuple[str, str, str]] = {
    "truth/sigma_BN": ("truth", "sigma_BN", "MRP"),
    "truth/omega_BN_B": ("truth", "omega_BN_B", "rad/s"),
    "truth/r_N": ("truth", "r_BN_N", "m"),
    "truth/v_N": ("truth", "v_BN_N", "m/s"),
    "est/sigma_BN": ("nav_att", "sigma_BN", "MRP"),
    "est/r_N": ("nav_trans", "r_BN_N", "m"),
    "est/v_N": ("nav_trans", "v_BN_N", "m/s"),
    "imu/gyro_P": ("imu", "AngVelPlatform", "rad/s"),
    "imu/accel_P": ("imu", "AccelPlatform", "m/s^2"),
}


def test_case(case_index, plant, draws, duration_s, run_writer) -> None:
    """One Monte Carlo case: boots the dead-reckoning flight software onto the already-
    dispersed `plant` fixture, runs it, writes its `run_<NNNN>.h5` via WiseDynamics' own
    writer, and checks that this repository's own analysis loader reads it back cleanly."""
    fsw_module = make_fsw(
        FSW_NAME,
        inputs=plant.readers(),
        initial_state=plant.initial_state,
        mu=plant.mu,
    )

    recorders = run_case(plant, fsw_module, duration_s=duration_s)
    assert len(recorders["truth"].times()) > 0, "scenario produced no recorded samples"

    arrays: dict[str, tuple[np.ndarray, str]] = {
        "t_s": (recorders["truth"].times() * macros.NANO2SEC, "s"),
    }
    for dataset_name, (recorder_name, field_name, units) in _EXPORT.items():
        data = np.array(getattr(recorders[recorder_name], field_name))
        arrays[dataset_name] = (data, units)

    extra_attrs = {f"draw_{name}": np.asarray(value) for name, value in draws.items()}
    run_path = run_writer(arrays, extra_attrs)

    load_run(run_path)  # raises RunDataError naming the file and the problem otherwise
