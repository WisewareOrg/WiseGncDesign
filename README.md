# WiseGncDesign

WiseGncDesign holds Wiseware's GNC flight software in Python, flown against simulated spacecraft
from [WiseDynamics](https://github.com/WisewareOrg/WiseDynamics), which `pyproject.toml` pins
under `[tool.uv.sources]`. The flight software runs at 1 Hz on the simulation's dynamics step,
50 Hz at its `hi` fidelity and 20 Hz at `med` and `lo`.

It has three parts:
- `gnc_algorithms`, each algorithm and its derivation as a literate module that imports as plain
  Python, with its math compiled by numba and its tests and Monte Carlo proof beside it. They name
  their inputs and outputs by the simulation's standard field names, so a host resolves them by
  name;
- `gnc_cdh`, which hosts an algorithm in the simulator ([`cdh/README.md`](cdh/README.md));
- `gnc_analysis.error_bounds`, which reads a run file with h5py and holds the dead reckoner's
  error to its accuracy bound.

## Development

Each algorithm is one notebook, `algorithms/gnc_algorithms/<name>.py`, a jupytext percent-format
module: its derivation, its code, its tests and its Monte Carlo proof. It imports as plain Python
and loads no simulator, and pytest collects its tests. The suite needs the simulator installed:
`just pinned` installs the WiseDynamics commit in `uv.lock`, and `just local` installs an editable
checkout (`$WISE_DYNAMICS_PATH`, default `../WiseDynamics`). Each recipe prints the WiseDynamics it
runs against, and each run file records which install wrote it.

```sh
just pinned   # or: just local
just kernel   # once: registers the `uv-project` Jupyter kernel the notebooks name
just lab      # JupyterLab in this environment
just test     # the whole suite
```

To run an algorithm's proof, open its `.py` in JupyterLab as a notebook (right-click, Open With,
Jupytext Notebook) on the `Python (uv)` kernel, save it, and run its `%%monte_carlo` cell: it runs
every case in parallel and writes one HDF5 run file per case under `monte_carlo/`. The cells after
it, which run in the notebook only, plot those runs. For the IMU dead reckoner that is
`algorithms/gnc_algorithms/imu_dead_reckoning.py`: four smoke tests of flight conditions with
closed forms, its 1 Hz cadence, and 852 cases that fly it in WiseDynamics' `Leo500` scenario and
hold each within the bound its drawn IMU biases imply.

CI (`.github/workflows/checks.yml`) runs, from the repository root:

```sh
uv sync --locked --group sim --group notebooks
uv run ruff check . && uv run ruff format --check .
uv run interrogate -v --fail-under 100 algorithms cdh analysis tests
uv run pydoclint algorithms cdh analysis tests
uv run pytest --ci
```

and executes the IMU dead reckoner's notebook with `jupytext --execute`.
