# Algorithms

`gnc_algorithms` holds the GNC algorithms. Each algorithm is a literate module: its derivation,
its code, the checks that verify it, and its figures, all in one file. Every module imports numpy
and the standard library. Nothing under `algorithms/` imports a simulation or flight framework,
so any host can run an algorithm unmodified.

## Module map

| Module | Public surface |
| --- | --- |
| `mrp.py` | MRP math for `sigma_BN`: `B` (kinematics matrix), `dcm_NB`, `shadow`, `compose`, `subtract`, `angle` |
| `imu_dead_reckoning.py` | strapdown dead reckoning: `ImuSample`, `DeadReckoningState`, `ImuDeadReckoner` |

## Conventions

- **Frames.**
  - `sigma_BN` is the MRP set of the body frame B with respect to the inertial frame N.
  - A suffix names the frame a vector is expressed in: `_N` inertial, `_B` body, and `_P` a
    sensor's platform frame.
- **Units.** Quantities are SI (m, m/s, m/s^2, rad, rad/s, m^3/s^2), and times are in s.
- **The algorithm class.** An algorithm the C&DH partition hosts is a class with these features:
  - it is constructed with a keyword `t0`, plus its initial state and parameters;
  - it exposes `state`, with a field `t`;
  - it advances with `step(sample)`;
  - its sample type is a dataclass with field `t`.

  `gnc_cdh.hosted` states this as protocols.

## Literate modules

The importable source of truth is a percent-format `.py` file. Each one pairs with
`notebooks/<module>.ipynb` through `jupytext.toml`. Either half can be edited:
`uv run jupytext --sync algorithms/gnc_algorithms/<module>.py` rewrites the stale half.

A module reads top to bottom as a document:
1. markdown cells carrying the derivation;
2. the code;
3. one `check_*` function per verified property, each under a markdown cell stating the property
   and its oracle;
4. optionally, `save_figures(out_dir)`, which writes the module's figures and returns their paths;
5. `run_checks`, which runs every `check_*` function.

Importing a module runs none of its checks. Three things do run them:
- `uv run python -m gnc_algorithms.<module>`, or running the notebook top to bottom in a kernel.
  Either runs `run_checks` and writes the figures under `figures/` in the working directory.
- `tests/algorithms/test_literate_checks.py`. It runs every `check_*` of every paired module as
  its own pytest case, and renders every module's figures.
- CI. It syncs every pair, requires a clean tree, and runs every module.

The collector proves each check passes and is the runner for local work. Running the module
proves the document executes top to bottom as a script, through its `__main__` path and its
figures. All three discover modules by the pairing and checks by name, so a new module or check
needs no registration.

## Example: step the dead reckoner by hand

A spacecraft in a circular 500 km orbit turns at 0.01 rad/s about body z, read by an ideal IMU.
After 60 one-second steps:
- the attitude is a 0.6 rad turn about z;
- the orbit radius holds.

```python
>>> import numpy as np
>>> from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample
>>> mu = 3.986004418e14  # m^3/s^2, Earth
>>> radius = 6_871_000.0  # m
>>> reckoner = ImuDeadReckoner(
...     sigma0_BN=np.zeros(3),
...     r0_N=[radius, 0.0, 0.0],
...     v0_N=[0.0, np.sqrt(mu / radius), 0.0],
...     t0=0.0,
...     mu=mu,
... )
>>> for k in range(1, 61):
...     state = reckoner.step(
...         ImuSample(t=float(k), omega_B=np.array([0.0, 0.0, 0.01]), accel_B=np.zeros(3))
...     )
>>> state.t
60.0
>>> bool(np.allclose(state.sigma_BN, [0.0, 0.0, np.tan(0.6 / 4.0)]))
True
>>> bool(abs(np.linalg.norm(state.r_N) - radius) < 1e-3)
True

```

`tests/algorithms/test_readme.py` runs this example.

## Adding an algorithm

1. Write `algorithms/gnc_algorithms/<name>.py` as a literate module, with at least one
   `check_*`.
2. Run `uv run jupytext --sync algorithms/gnc_algorithms/<name>.py` to create
   `notebooks/<name>.ipynb`, and commit both halves.
3. To host it in a simulator, register a binding and resolve its signals for the transport
   ([`cdh/README.md`](../cdh/README.md#adding-an-algorithm)).
4. Add a scenario test under `tests/sim/` ([`tests/README.md`](../tests/README.md)).
