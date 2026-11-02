# Analysis

`gnc_analysis` loads recorded runs and grades the flight software's navigation estimate against
truth.

It grades independently of what it measures. It computes attitude error with its own MRP math, in
`gnc_analysis.mrp`, and reads runs only through files. Nothing under `analysis/` imports
`gnc_algorithms`, `gnc_cdh`, Basilisk or WiseDynamics.

## Module map

| Module | Public surface |
| --- | --- |
| `runs.py` | `load_run`, `load_campaign`, `Run` (with `Truth`, `Estimate`, `ImuReadings`), `DATASETS`, `RunDataError` |
| `navigation_error.py` | per-run metrics `attitude_error_deg`, `position_error_m`, `velocity_error_m_s`; `summarize`, `write_report`, `analyze`; `main`, the `gnc-analyze` command |
| `mrp.py` | `subtract`, `angle`, `to_quaternion`, `from_quaternion` for `sigma_BN`, batched over a leading dimension |

## What a run file must contain

A run is one HDF5 file, `run_<NNNN>.h5`, with the case number zero-padded to 4 digits. A campaign
is a directory of run files sharing one `t_s`. `gnc_analysis.runs` is the single statement of this
layout. The table below states the same layout for readers, and
`tests/analysis/test_runs.py` holds the two equal.

Every dataset must meet these rules:
- it is float64;
- it carries a string attribute `units` equal to the value shown;
- it has `N = len(t_s)` rows;
- every value is finite.

| Dataset | Shape | Units | Meaning |
| --- | --- | --- | --- |
| `t_s` | `(N,)` | `s` | sample times, strictly increasing from 0 |
| `truth/sigma_BN` | `(N, 3)` | `MRP` | true attitude, B with respect to N |
| `truth/omega_BN_B` | `(N, 3)` | `rad/s` | true angular rate of B with respect to N, in B |
| `truth/r_N` | `(N, 3)` | `m` | true inertial position |
| `truth/v_N` | `(N, 3)` | `m/s` | true inertial velocity |
| `est/sigma_BN` | `(N, 3)` | `MRP` | estimated attitude, B with respect to N |
| `est/r_N` | `(N, 3)` | `m` | estimated inertial position |
| `est/v_N` | `(N, 3)` | `m/s` | estimated inertial velocity |
| `imu/gyro_P` | `(N, 3)` | `rad/s` | gyro output, in the IMU's platform frame P |
| `imu/accel_P` | `(N, 3)` | `m/s^2` | accelerometer output, non-gravitational, in P |

The root attributes are:
- `case` and `seed`, both integers, required;
- every `draw_<name>`, collected into `Run.draws["<name>"]`;
- every `versions_<name>`, collected into `Run.versions["<name>"]`.

Other datasets and attributes are ignored. `load_run` raises `RunDataError` naming the file and the
dataset, attribute or rule at fault. `load_campaign` raises it naming the first run whose `t_s`
differs.

## Metrics

Each metric is computed per run at every sample:
- **attitude error, deg:** `4·atan(|σ_truth ⊖ σ_est|)`, the principal angle of the truth attitude
  relative to the estimate;
- **position error, m:** `|r_truth − r_est|`;
- **velocity error, m/s:** `|v_truth − v_est|`.

Across a campaign, `summarize` reports for each metric:
- the mean, standard deviation, 3σ and maximum of each run's final value;
- a growth rate, the slope of a linear fit of the ensemble RMS against time.

## Running the analysis on a directory

`gnc-analyze` needs the `analysis` extra, h5py and matplotlib: install
`wise-gnc-design[analysis]`. In this repository `uv sync` installs it.

```sh
uv run gnc-analyze campaign --out report
```

The argument is one run file or a campaign directory. The command writes three things into
`report/`:
- `summary.md`, holding the run count, the duration and the statistics above;
- `attitude_error.png`, `position_error.png` and `velocity_error.png`, each drawing every run
  faintly and the ensemble mean and ±3σ in bold.

It returns 0 on success. It returns 1 when the loader rejects the input, printing the loader's
message on stderr. A usage error returns 2. CI runs this command on the campaign its scenario tests
write.

From Python, `analyze(path, out_dir)` does the same and returns the `Summary`. `summarize(runs)`
computes the `Summary` without writing anything:

```python
from gnc_analysis.navigation_error import summarize
from gnc_analysis.runs import load_campaign

summary = summarize(load_campaign("campaign"))
attitude = summary.metrics[0]
print(attitude.metric.label, attitude.final_max, attitude.metric.unit)
```
