# WiseGncDesign

WiseGncDesign is the flight and analysis home for Wiseware's GNC work. GNC algorithms live under
`algorithms/`, framework-free — no simulation or flight-framework import or include anywhere
under that directory — Python primary with C++ variants, so the same algorithm can be hosted
unmodified wherever it runs. `gnc_cdh/` is the C&DH (command and data handling) partition: a
transport-independent data dictionary of each algorithm's input and output fields, resolved by
each transport (Basilisk, an F' host, a cFS host, and others to follow) in its own sibling
directory. `analysis/` scores recorded runs for attitude, position and velocity error against
truth, independent of which simulation produced them.

Flight, simulation and analysis are split so any can be replaced without touching the others:
framework-free algorithms and run analysis both live here, in WiseGncDesign; simulation plants
and Monte Carlo campaigns that import those algorithms and write the runs analysis reads live in
[WiseDynamics](https://github.com/WisewareOrg/WiseDynamics).

## Layout

- `algorithms/` — framework-free GNC algorithms (see its own `README.md`).
- `gnc_cdh/` — the C&DH partition: a transport-independent data dictionary, resolved by each
  transport as a sibling directory (see its own `README.md`).
- `analysis/gnc_analysis/` — attitude, position and velocity error analysis over recorded runs
  (see "Analysis" below).
- `scripts/check-no-framework.sh` — the gate that keeps `algorithms/` framework-free.
- `docs/decisions/` — this repository's ADRs (none yet).

## Analysis

`analysis/gnc_analysis/` scores recorded runs for attitude, position and velocity error against
truth. Its loader, `analysis/gnc_analysis/runs.py`, is the sole statement of what a run file
must contain; `gnc-analyze <path> --out <dir>` runs the analysis over one run file or a
directory of them.

### What a run file must contain

A run is one HDF5 file, `run_<NNNN>.h5` (zero-padded to 4 digits); a campaign is a directory of
them. The loader (`analysis/gnc_analysis/runs.py`) reads these datasets, each `float64` with a
string `units` attribute matching the value shown:

| Dataset | Shape | Units |
| --- | --- | --- |
| `t_s` | `(N,)` | `s` — strictly increasing, starting at 0 |
| `truth/sigma_BN` | `(N, 3)` | `MRP` |
| `truth/omega_BN_B` | `(N, 3)` | `rad/s` |
| `truth/r_N` | `(N, 3)` | `m` |
| `truth/v_N` | `(N, 3)` | `m/s` |
| `est/sigma_BN` | `(N, 3)` | `MRP` |
| `est/r_N` | `(N, 3)` | `m` |
| `est/v_N` | `(N, 3)` | `m/s` |
| `imu/gyro_P` | `(N, 3)` | `rad/s` (sensor frame) |
| `imu/accel_P` | `(N, 3)` | `m/s^2` (sensor frame) |

`load_run` reads each of these by name, checks its `units` attribute, rejects a `NaN` anywhere,
and requires `t_s` to be strictly increasing from 0; `load_campaign` requires every run in a
directory to share the same `t_s`. Extra datasets and attributes are ignored. This loader, and
the behavior above, is the sole authority on what a run file must contain.
