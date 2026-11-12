# WiseGncDesign

WiseGncDesign holds Wiseware's GNC flight software in two builds side by side, Python and F´ (C++),
flown against simulated spacecraft from [WiseDynamics](https://github.com/WisewareOrg/WiseDynamics),
which `pyproject.toml` pins under `[tool.uv.sources]`. The flight software runs at 1 Hz on the
simulation's dynamics step, 50 Hz at its `hi` fidelity, 20 Hz at `med` and 10 Hz at `lo`.

The repository's parts are laid out under Development.

## Development

### Layout

```text
harness/       mission.py, requirements_tree.py, judging.py (a pytest plugin), notebook.py, runs.py
analysis/      one analyzer per metric: its limits, error math and plot
scenarios/     how each scenario a TST item references is flown
algorithms/gnc_algorithms/<name>/   notebook, its F´ component, gross check, tests, and an __init__
                                    re-exporting the notebook
missions/      notebooks that plan missions, and the test running them
cdh/           gnc_cdh, the Python and F´ hosts and a worked example; fprime/, the F´ project
docs/          requirements/ (Doorstop tree), decisions/ (ADRs)
```

Tests sit beside the code they test. The suite needs the simulator installed, from `just pinned`
(the WiseDynamics commit in `uv.lock`) or `just local` (an editable checkout at
`$WISE_DYNAMICS_PATH`, default `../WiseDynamics`).

### The F´ build

`just pinned` and `just local` also build the F´ deployment. Besides `uv.lock`, the build needs the
system C++ compiler and git. The F´ framework and Eigen are fetched by tag into gitignored folders
under `cdh/fprime/lib/`, outside the build cache, so a sync needs network access to GitHub and
GitLab only the first time, or when a tag changes. Each sync rebuilds the F´ build cache from
scratch, which needs no network.

`just test`, `just fly` and `just lab` rebuild the F´ extension first, so an edit to C++ or FPP is
picked up. That rebuild reuses the existing cache, so after switching branches run `just pinned` or
`just local` to rebuild it from scratch. Why the F´ build flies inside the simulation, and how, is
in [ADR 0003 rev 1](docs/decisions/0003-fly-the-fprime-flight-software-inside-the-basilisk-process.md).

### Requirements and missions

`docs/requirements/` is a Doorstop tree: SYS items are capabilities, SRS items are rungs of
performance with `x`, `p` and `c` as attributes, and TST items are scenarios linked to the rungs they
evaluate. Its items and values are placeholders for exercising the tooling. `just reqs` checks that
every item and link is reviewed and that no file a TST references has changed since.

A mission is a vehicle, an FSW builder and the scenarios to fly, defined as a value in a notebook.
The builder claims its capabilities with `@provides("SYS...")`, and a flight is judged on the rungs
its scenario links to that sit under those capabilities. `mission_tests` turns missions into Monte
Carlo tests: a class per vehicle holding a test per FSW and scenario. The reasoning is in
[ADR 0002 rev 2](docs/decisions/0002-fly-missions-from-notebooks-against-a-requirements-tree.md).

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

A Monte Carlo test flies two cases, into the reserved `scratch` session, unless `--full-monte-carlo`
is passed. The `%%monte_carlo` cell and `just fly` pass it; bare `pytest`, the VS Code test explorer,
`just test` and CI do not.

```sh
just session <name>
just fly missions/dead_reckoner_leo.py          # a notebook's full flight, into the active session
uv run --no-sync pytest missions/dead_reckoner_leo.py --full-monte-carlo   # the same, spelled out
```

### Judging

`just judge` runs the requirement analyzers in `analysis/`, outside `testpaths` so `just test` never
judges, over the active session. `judge()` in a notebook does the same and returns the matrix, a row
per rung and a column per flight. A failing rung lists each failing case with the command that
re-simulates it. The report lands in the session's `report/` and is rebuilt on every judging; start
at `report/matrix.md`. How a verdict is reached is in
[ADR 0002 rev 2](docs/decisions/0002-fly-missions-from-notebooks-against-a-requirements-tree.md) and
[ADR 0001 rev 3](docs/decisions/0001-judge-monte-carlo-sessions-with-requirement-analyzers.md).

### Recipes and CI

`just --list` shows every recipe with its description. `.github/workflows/checks.yml` is the
authority on what CI runs: lint and docstring coverage, `just reqs`, and the suite.
