# Tests

`uv run pytest` runs every tier below. The tiers mirror the packages.

| Tier | What it proves |
| --- | --- |
| `algorithms/` | every `check_*` of every literate module passes; the modules with a notebook are exactly the modules defining checks, subpackages included, and every notebook belongs to one or to a notebook document, by the rule in `literate_documents.py` that CI's literate job also uses; every module's figures render; and `algorithms/README.md`'s example runs |
| `cdh/` | `AlgorithmModule`, `make_fsw` and every binding, against standalone Basilisk messages |
| `analysis/` | the grader's MRP math against an axis-angle oracle; every rule of the run-file loader; each term of the accuracy bound against its hand-computed value; the summary statistics and `gnc-analyze` against synthetic runs with closed-form errors |
| `sim/` | the dead reckoner, hosted by `gnc_cdh.basilisk` on a WiseDynamics plant, stays within bounds derived from each case's drawn IMU biases, and writes a run file the loader accepts |
| `notebooks/` | each Monte Carlo document imports without running, reads its counts through `MonteCarloSettings` from its two environment variables, finds the repository root, and refuses a run directory holding other than the requested run count |
| `session/` | the session check below, run under `pytest -n 2` in a temporary tree |

## Scenario tests and Monte Carlo runs

`tests/sim/` runs against the WiseDynamics release pinned in `pyproject.toml`, installed by
`uv sync --group sim`. Without that group, the tier skips. With `REQUIRE_SIM=1`, which CI sets, a
missing WiseDynamics or h5py fails the session instead.

WiseDynamics registers a pytest plugin through its `pytest11` entry point. Installing it is
enough, and this repository declares nothing to load it. The plugin's options:

| Option | Meaning |
| --- | --- |
| `--sim-runs N` | number of cases; the scenario test is parametrized over `sim_case_index` in `range(N)` |
| `--sim-out DIR` | run directory receiving `run_<NNNN>.h5` (default: a fresh temporary directory) |
| `--sim-seed S` | session seed; each case draws from its own child stream of it |
| `--sim-duration-s T` | simulated duration of each case, in s |
| `--sim-spacecraft NAME` | the plant to build |

Its fixtures, used by `tests/sim/test_imu_dead_reckoning.py`:

| Fixture | Value |
| --- | --- |
| `sim_case_index` | this case's index |
| `sim_duration_s` | the case's simulated duration, in s, from `--sim-duration-s` |
| `sim_draws` | this case's dispersed plant configuration values |
| `sim_plant` | the plant built with those draws and its own noise seed |
| `sim_run_writer(datasets, extra_attrs=None)` | writes this case's run file and returns its path |

WiseDynamics documents them in full in its `wise_dynamics/basilisk/README.md`.

One case reruns alone, with the draws and noise it had in its session:

```sh
uv run pytest --sim-seed S --sim-runs N "tests/sim/test_imu_dead_reckoning.py::test_imu_dead_reckoning_case[k]"
```

## The session check

Each scenario case records its run file with `record_property("run_file", path)`. At the end of
a session, `tests/conftest.py` checks three things on the controlling process:
- the recorded files share one directory, the run directory, which is `--sim-out` when that
  option is given;
- they are exactly the `run_*.h5` files in it;
- the directory loads through `gnc_analysis.runs.load_run_directory`.

It names every missing or stale file and any file the loader rejects, and fails the session. On
success it prints one line: `session check: N run files loaded from DIR`. CI requires that line.
