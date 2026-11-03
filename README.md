# WiseGncDesign

WiseGncDesign holds Wiseware's GNC flight software in Python, flown against simulated spacecraft
from [WiseDynamics](https://github.com/WisewareOrg/WiseDynamics), which `pyproject.toml` pins
under `[tool.uv.sources]`. The flight software runs at 1 Hz on the simulation's 50 Hz dynamics
step.

## Layout

| Path | What it holds |
| --- | --- |
| `algorithms/` | `gnc_algorithms`: each algorithm as a literate module (percent-format `.py`), its notebook, ending with its Monte Carlo run against its bound; `mrp` holds the attitude math it uses |
| [`cdh/`](cdh/README.md) | `gnc_cdh`: the data dictionary, and the Basilisk host module that computes an algorithm at 1 Hz |
| `analysis/` | `gnc_analysis.error_bounds`: a run file read with h5py, and the dead reckoner's error against its accuracy bound |
| `tests/` | `cdh/` the host module and the data dictionary; `sim/` the scenario test and the estimate's 1 Hz cadence, which skip without the `sim` group and fail instead with `REQUIRE_SIM=1` |
| `docs/decisions/` | this repository's architecture decision records |

## Development

Every command runs from the repository root, and CI runs each of them
(`.github/workflows/checks.yml`).

```sh
uv sync --locked --group sim
uv run ruff check . && uv run ruff format --check .
uv run pytest -n 2 --sim-runs 2
uv run python -m gnc_algorithms.imu_dead_reckoning
```

The scenario test, `tests/sim/test_imu_dead_reckoning.py`, flies the dead reckoner in
WiseDynamics' `Leo500` scenario, writes one HDF5 run file per case, and holds each case within the
bound its drawn IMU biases imply. Its `--sim-*` options come from WiseDynamics' pytest plugin.

The dead reckoner's module is its notebook: what the integrator is, its code, then a Monte Carlo
run of that test over `GNC_MONTE_CARLO_RUNS` cases (default 852) on `GNC_MONTE_CARLO_WORKERS`
workers (default the CPU count), showing each error against its bound and the final errors. The
bound is the requirement it meets. To open it in Jupyter, generate the notebook from its source;
generated notebooks are ignored by git:

```sh
uv run jupytext --to ipynb algorithms/gnc_algorithms/imu_dead_reckoning.py
uv run --with jupyterlab jupyter lab algorithms/gnc_algorithms/
```
