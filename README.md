# WiseGncDesign

WiseGncDesign holds Wiseware's GNC flight software in Python, flown against simulated spacecraft
from [WiseDynamics](https://github.com/WisewareOrg/WiseDynamics), which `pyproject.toml` pins
under `[tool.uv.sources]`. The flight software runs at 1 Hz on the simulation's dynamics step,
50 Hz at its `hi` fidelity, 20 Hz at `med` and 10 Hz at `lo`.

It has these parts:
- `algorithms/gnc_algorithms/<name>/`, each algorithm as a package around its notebook, which holds
  the derivation and the implementation side by side, with its math compiled by numba. Importing
  one loads the simulator stack and runs nothing. Algorithms name their inputs and outputs by the
  simulation's standard field names, so a host resolves them by name;
- `cdh/`, `gnc_cdh`, which hosts an algorithm in the simulator ([`cdh/README.md`](cdh/README.md));
- `harness/`, the machinery that flies and judges missions and knows no specific requirement,
  metric or scenario;
- `analysis/`, the requirement analyzers, one per metric;
- `scenarios/`, how each scenario is flown;
- `missions/`, notebooks that plan missions;
- `docs/requirements/`, the Doorstop requirements tree.

## Development

### Layout

```text
harness/       mission.py, requirements_tree.py, judging.py (a pytest plugin), notebook.py, runs.py
analysis/      one analyzer per metric: its limits, error math and plot
scenarios/     how each scenario a TST item references is flown
algorithms/gnc_algorithms/<name>/   notebook, gross check, tests, and an __init__ re-exporting the notebook
missions/      notebooks that plan missions, and the test running them
cdh/           the Basilisk host and its worked example
docs/          requirements/ (Doorstop tree), decisions/ (ADRs)
```

Tests sit beside the code they test. The suite needs the simulator installed, from `just pinned`
(the WiseDynamics commit in `uv.lock`) or `just local` (an editable checkout at
`$WISE_DYNAMICS_PATH`, default `../WiseDynamics`).

### Requirements and missions

`docs/requirements/` is a Doorstop tree: SYS items are capabilities, SRS items are rungs of
performance with `x`, `p` and `c` as attributes, and TST items are scenarios linked to the rungs they
evaluate. Its items and values are placeholders for exercising the tooling. `just reqs` checks that
every item and link is reviewed and that no file a TST references has changed since.

A mission is a vehicle, an FSW builder and the scenarios to fly, defined as a value in a notebook.
The builder claims its capabilities with `@provides("SYS...")`, and a flight is judged on the rungs
its scenario links to that sit under those capabilities. `mission_tests` turns missions into Monte
Carlo tests: a class per vehicle holding a test per FSW and scenario. The reasoning is in
[ADR 0002 rev 1](docs/decisions/0002-fly-missions-from-notebooks-against-a-requirements-tree.md).

### Notebooks

An algorithm notebook, `algorithms/gnc_algorithms/<name>/<name>.py`, holds the algorithm's
derivation and implementation, then its mission, then cells that run in the notebook only and judge
and plot. A mission notebook in `missions/` plans missions instead, such as one algorithm on several
vehicles. Each is a jupytext percent-format `.py`, the source of truth, paired with an `.ipynb`
beside it that git ignores. The `.py` records no kernel; the `.ipynb` keeps the kernel chosen on the
machine, and a headless run uses the registered `wise-gnc-design` kernel.

To work in a notebook, run `just pinned` or `just local`, which sync the environment, register the
kernel and create the `.ipynb` files, then `just lab` and open the `.ipynb` on the `WiseGncDesign`
kernel. Pick a session first, run the `%%monte_carlo` cell to fly the mission, then call `judge()`
for the matrix and `plots("<SRS ID>")` for a rung's plots.

### Sessions and flying

Monte Carlo tests refuse to run without an active session, a named folder under `monte_carlo/`.
`just session <name>` makes `<name>` active, and `just session` with no name lists the sessions.
Each flight's runs land under the session in a folder of its own, so several vehicles and notebooks
share one session.

A Monte Carlo test flies two cases unless `--full-monte-carlo` is passed, and capped runs go into
the reserved `scratch` session whatever session is active. The `%%monte_carlo` cell and `just fly`
fly the full campaign. Bare `pytest`, the VS Code test explorer, `just test` and CI do not.

```sh
just session <name>
just fly missions/dead_reckoner_leo.py          # a notebook's full flight, into the active session
uv run --no-sync pytest missions/dead_reckoner_leo.py --full-monte-carlo   # the same, spelled out
```

### Judging

`just judge` runs the requirement analyzers in `analysis/`, outside `testpaths` so `just test` never
judges, over the active session. `judge()` in a notebook does the same and returns the matrix, a row
per rung and a column per flight. Each analyzer judges one metric for every rung whose tree item
references its file. A rung's verdict compares each run with `x`, then the failures with the number
the `n` runs found allow at `p` and `c`. A crash record counts as a failed case. A failing rung lists
each failing case with the command that re-simulates it.

The report lands in the session's `report/` and is rebuilt on every judging; start at
`report/matrix.md`. Folders without a `flight.json` or whose test file is gone are skipped and listed
there. The judge reads what a flight recorded when it flew and never executes a notebook. The
reasoning is in
[ADR 0001 rev 2](docs/decisions/0001-judge-monte-carlo-sessions-with-requirement-analyzers.md).

### Recipes

| Recipe | What it does |
|---|---|
| `just pinned` | Sync the environment at the WiseDynamics commit in `uv.lock`, register the kernel, and sync the notebooks. |
| `just local` | The same with an editable WiseDynamics checkout. |
| `just lab` | Open JupyterLab in this environment. |
| `just session [name]` | Make `name` the active session, or list the sessions. |
| `just fly <notebook>` | Fly a notebook's Monte Carlo tests headless at full count into the active session; extra arguments go to pytest. |
| `just test` | The suite: every Monte Carlo capped at two cases, each notebook run end to end in a kernel. |
| `just judge` | Judge the active session. |
| `just reqs` | Check the requirements tree with `check-reqs`. |

### CI

CI (`.github/workflows/checks.yml`) runs, from the repository root:

```sh
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run interrogate -v --fail-under 100 algorithms cdh analysis harness scenarios missions
uv run pydoclint algorithms cdh analysis harness scenarios missions
just reqs
uv sync --locked --group sim --group notebooks
uv run --no-sync python -m ipykernel install --sys-prefix --name wise-gnc-design --display-name "WiseGncDesign"
uv run --no-sync pytest
```
