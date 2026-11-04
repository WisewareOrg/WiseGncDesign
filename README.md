# WiseGncDesign

WiseGncDesign holds Wiseware's GNC flight software in Python, flown against simulated spacecraft
from [WiseDynamics](https://github.com/WisewareOrg/WiseDynamics), which `pyproject.toml` pins
under `[tool.uv.sources]`. The flight software runs at 1 Hz on the simulation's dynamics step,
50 Hz at its `hi` fidelity and 20 Hz at `med` and `lo`.

It has three parts:
- `gnc_algorithms`, each algorithm and its derivation as a literate module that imports as plain
  Python, with its math compiled by numba. The algorithms depend on numpy and numba only, with
  SciPy for numba's matrix products, and name their inputs and outputs by the simulation's standard
  field names, so a host resolves them by name;
- `gnc_cdh`, which hosts an algorithm in the simulator ([`cdh/README.md`](cdh/README.md));
- `gnc_analysis.error_bounds`, which reads a run file with h5py and holds the dead reckoner's
  error to its accuracy bound.

## Development

Every command runs from the repository root, and CI runs each of them
(`.github/workflows/checks.yml`).

```sh
uv sync --locked --group sim
uv run ruff check . && uv run ruff format --check .
uv run interrogate -v --fail-under 100 algorithms cdh analysis notebooks tests
uv run pydoclint algorithms cdh analysis notebooks tests
uv run pytest -n 2 --sim-runs 2
uv run python notebooks/imu_dead_reckoning_monte_carlo.py
```

All of the dead reckoner's tests are in `tests/sim/test_imu_dead_reckoning.py`: four smoke tests
of flight conditions with closed forms, its 1 Hz cadence, and the Monte Carlo case, which flies the
dead reckoner in WiseDynamics' `Leo500` scenario, writes one HDF5 run file per case, and holds each
case within the bound its drawn IMU biases imply. Its `--sim-*` options come from WiseDynamics'
pytest plugin.

The notebook runs that module through pytest over `GNC_MONTE_CARLO_RUNS` cases (default 852) on
`GNC_MONTE_CARLO_WORKERS` workers (default the CPU count) at `GNC_MONTE_CARLO_FIDELITY` (default
`lo`), then shows each error against its bound and the final errors. It holds no test logic.

`jupytext.toml` pairs the Monte Carlo notebook's and the dead reckoner's percent-format sources
with the `.ipynb` beside each, which git ignores. To open them in any JupyterLab, regenerate the
`.ipynb` files from their sources, then open them on a kernel that runs this environment's Python:

```sh
uv run jupytext --sync notebooks/imu_dead_reckoning_monte_carlo.py algorithms/gnc_algorithms/imu_dead_reckoning.py
```

Or run JupyterLab from this environment: the `notebooks` group adds JupyterLab, jupytext with its
lab extension, and ipykernel.

```sh
uv sync --locked --group sim --group notebooks
uv run jupyter lab
```

There, open either `.py` with right-click, Open With, Jupytext Notebook, on the environment's
Python 3 (ipykernel) kernel. Neither file names a kernel, so any JupyterLab keeps its own choice.
