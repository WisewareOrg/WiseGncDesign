# Tests

`uv run pytest` runs every tier below. The tiers mirror the packages.

| Tier | What it proves |
| --- | --- |
| `algorithms/` | every `check_*` of every literate module passes, every module's figures render, and `algorithms/README.md`'s example runs |
| `cdh/` | `AlgorithmModule`, `make_fsw` and every binding, against standalone Basilisk messages |
| `analysis/` | the grader's MRP math against an axis-angle oracle; every rule of the run-file loader; the summary statistics and `gnc-analyze` against synthetic runs with closed-form errors |
| `sim/` | the dead reckoner, hosted by `gnc_cdh.basilisk` on a WiseDynamics plant, stays within bounds derived from each case's drawn IMU biases, and writes a run file the loader accepts |
| `test_campaign_check.py` | the campaign check below, run under `pytest -n 2` in a temporary tree |

## Scenario tests and campaigns

`tests/sim/` runs against the WiseDynamics release pinned in `pyproject.toml`, installed by
`uv sync --group sim`. Without that group, the tier skips. With `REQUIRE_SIM=1`, which CI sets, a
missing WiseDynamics or h5py fails the session instead.

WiseDynamics registers a pytest plugin through its `pytest11` entry point. Installing it is
enough, and this repository declares nothing to load it. The plugin's options:

| Option | Meaning |
| --- | --- |
| `--sim-runs N` | number of cases; the scenario test is parametrized over `sim_case_index` in `range(N)` |
| `--sim-out DIR` | campaign directory receiving `run_<NNNN>.h5` (default: a fresh temporary directory) |
| `--sim-seed S` | campaign seed; each case draws from its own child stream of it |
| `--sim-duration-s T` | simulated duration of each case, in s |
| `--sim-spacecraft NAME` | the plant to build |

Its fixtures, used by `tests/sim/test_imu_dead_reckoning.py`:

| Fixture | Value |
| --- | --- |
| `sim_campaign` | the session's campaign settings, from the options above |
| `sim_case_index` | this case's index |
| `sim_draws` | this case's dispersed plant configuration values |
| `sim_plant` | the plant built with those draws and its own noise seed |
| `sim_run_writer(datasets, extra_attrs=None)` | writes this case's run file and returns its path |

WiseDynamics documents them in full in its `wise_dynamics/basilisk/README.md`.

## The campaign check

Each scenario case records its run file with `record_property("run_file", path)`. At the end of
a session, `tests/conftest.py` checks two things on the controlling process:
- the recorded files are exactly the `run_*.h5` files in the campaign directory;
- the directory loads through `gnc_analysis.runs.load_campaign`.

It names every missing or stale file and any file the loader rejects, and fails the session. On
success it prints one line: `campaign check: N runs loaded from DIR`. CI requires that line.
