# WiseGncDesign

WiseGncDesign holds Wiseware's GNC flight software in Python, flown against simulated spacecraft
from [WiseDynamics](https://github.com/WisewareOrg/WiseDynamics), which `pyproject.toml` pins
under `[tool.uv.sources]`. The flight software runs at 1 Hz on the simulation's dynamics step,
50 Hz at its `hi` fidelity and 20 Hz at `med` and `lo`.

It has three parts:
- `gnc_algorithms`, each algorithm and its derivation as a literate module, with its math compiled
  by numba. Importing one loads the simulator stack and runs nothing. They name their inputs and
  outputs by the simulation's standard field names, so a host resolves them by name;
- `gnc_cdh`, which hosts an algorithm in the simulator ([`cdh/README.md`](cdh/README.md));
- `gnc_analysis`, which holds the error bounds (it reads a run file with h5py and holds the dead
  reckoner's error to its accuracy bound) and the support for the requirement analyzers in
  `analysis/`: the allowed-failures rule and the metric the requirement tests judge
  with. `just judge` runs the analyzers.

## Development

Each algorithm is one notebook, `algorithms/gnc_algorithms/<name>.py`: a jupytext percent-format
module whose import loads the simulator stack and runs nothing, and whose tests pytest collects.
The suite needs the simulator installed, from `just pinned` (the WiseDynamics commit in `uv.lock`)
or `just local` (an editable checkout at `$WISE_DYNAMICS_PATH`, default `../WiseDynamics`).

```sh
just pinned
just lab
just session <name>
just test
```

Monte Carlo tests refuse to run without an active session, so pick one with `just session <name>`
before `just test` and before running a notebook's `%%monte_carlo` cell.

A Monte Carlo test writes its runs into the active session, a named folder under `monte_carlo/`.
`just session <name>` makes `<name>` active, and `just session` with no name lists the sessions.
`just judge` judges the active session: it runs the requirement analyzers in `analysis/`, which are
outside `testpaths` so `just test` never judges. Each analyzer gives one requirement a verdict over
the tests that claim it with `@pytest.mark.verifies("<ID>")`, and `report/matrix.md` and the
requirement plots land in the session. A crash record counts as one failed case against the allowed
failures. A case with neither a run nor a crash record leaves its test not judged. The reasoning is
in [ADR 0001 rev 1](docs/decisions/0001-judge-monte-carlo-sessions-with-requirement-analyzers.md).

Setup creates an `.ipynb` beside each algorithm `.py`. To run an algorithm's proof, open the
`.ipynb` in VS Code or JupyterLab on the `WiseGncDesign` kernel, save it, and run its
`%%monte_carlo` cell. The cell after it, which runs in the notebook only, plots the runs, which
land in `monte_carlo/`. The IMU dead reckoner is `algorithms/gnc_algorithms/imu_dead_reckoning.py`.

CI (`.github/workflows/checks.yml`) runs, from the repository root:

```sh
uv sync --locked --group sim --group notebooks
just session ci
uv run ruff check . && uv run ruff format --check .
uv run interrogate -v --fail-under 100 algorithms cdh analysis tests
uv run pydoclint algorithms cdh analysis tests
uv run pytest --ci
```

and executes the IMU dead reckoner's notebook with `jupytext --execute`.
