"""One IMU on a tumbling spacecraft: `gnc_cdh.basilisk`'s `imu_dead_reckoning` flight software,
built on WiseDynamics' plant, writes one run file per case via WiseDynamics' own writer, read
back by this repository's own analysis loader."""

import numpy as np
from Basilisk.utilities import macros
from gnc_analysis.runs import load_run
from sim.basilisk.run import run_case

from gnc_cdh.basilisk import make_fsw
from gnc_cdh.basilisk.signals import SIGNALS
from gnc_cdh.bindings import BINDINGS

FSW_NAME = "imu_dead_reckoning"

# README's "What a run file must contain": dataset name -> units, for the plant's own truth and
# IMU recorders (WiseDynamics' own vocabulary, not the C&DH dictionary's).
_TRUTH_AND_IMU_EXPORT: dict[str, tuple[str, str, str]] = {
    "truth/sigma_BN": ("truth", "sigma_BN", "MRP"),
    "truth/omega_BN_B": ("truth", "omega_BN_B", "rad/s"),
    "truth/r_N": ("truth", "r_BN_N", "m"),
    "truth/v_N": ("truth", "v_BN_N", "m/s"),
    "imu/gyro_P": ("imu", "AngVelPlatform", "rad/s"),
    "imu/accel_P": ("imu", "AccelPlatform", "m/s^2"),
}

# The units each neutral signal carries, keyed by signal name — the one place a unit is stated.
_UNITS = {
    "angular_rate": "rad/s",
    "specific_force": "m/s^2",
    "sigma_BN": "MRP",
    "r_N": "m",
    "v_N": "m/s",
}


def _estimate_export() -> dict[str, tuple[str, str, str]]:
    """Derives {dataset_name: (role, payload_field, units)} for the estimate's own datasets
    directly from gnc_cdh's data dictionary and Basilisk signals table (the same ones make_fsw
    itself resolves against), so a role, field or unit swapped in one place cannot pass here
    without also breaking the flight software's own wiring."""
    binding = BINDINGS[FSW_NAME]
    export: dict[str, tuple[str, str, str]] = {}
    for role, state_attrs in binding.outputs.items():
        for state_attr, signal in state_attrs.items():
            _, payload_field = SIGNALS[(role, signal)]
            export[f"est/{state_attr}"] = (role, payload_field, _UNITS[signal])
    return export


def test_case(case_index, plant, duration_s, run_writer) -> None:
    """One Monte Carlo case: boots the dead-reckoning flight software onto the already-
    dispersed `plant` fixture, runs it, writes its `run_<NNNN>.h5` via WiseDynamics' own
    writer, and checks that this repository's own analysis loader reads it back cleanly."""
    fsw_module = make_fsw(
        FSW_NAME,
        inputs=plant.readers(),
        initial_state=plant.initial_state,
        mu=plant.mu,
    )
    fsw_outputs = {role: msg for role, (_, msg) in fsw_module.outputs.items()}

    recorders = run_case(plant, fsw_module, fsw_outputs, duration_s=duration_s)
    assert len(recorders["truth"].times()) > 0, "scenario produced no recorded samples"

    export = {**_TRUTH_AND_IMU_EXPORT, **_estimate_export()}
    arrays: dict[str, tuple[np.ndarray, str]] = {
        "t_s": (recorders["truth"].times() * macros.NANO2SEC, "s"),
    }
    for dataset_name, (recorder_name, field_name, units) in export.items():
        data = np.array(getattr(recorders[recorder_name], field_name))
        arrays[dataset_name] = (data, units)

    run_path = run_writer(arrays)

    load_run(run_path)  # raises RunDataError naming the file and the problem otherwise
