"""Importing an algorithm module loads no simulator."""

import subprocess
import sys


def test_importing_an_algorithm_loads_neither_wise_dynamics_nor_basilisk():
    """`import gnc_algorithms.imu_dead_reckoning` leaves `wise_dynamics` and `Basilisk` unloaded."""
    code = (
        "import sys, gnc_algorithms.imu_dead_reckoning\n"
        "loaded = [m for m in ('wise_dynamics', 'Basilisk') if m in sys.modules]\n"
        "sys.exit(f'loaded {loaded}' if loaded else 0)"
    )

    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
