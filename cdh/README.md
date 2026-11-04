# C&DH

`gnc_cdh` is the C&DH (command and data handling) partition. It hosts an algorithm from
`gnc_algorithms` in a simulator, and knows nothing about what any field means: it copies message
fields to the algorithm's `step` as plain arrays and the arrays it returns into messages, by
name. Frames, mountings and units belong to the algorithm.

`gnc_cdh.basilisk` hosts algorithms in Basilisk. Each algorithm has one `Binding` in `BINDINGS`,
which declares:
- `algorithm`: the algorithm class;
- `inputs`: each `step` keyword and the `(input role, message field)` it is copied from;
- `outputs`: each name `step` returns and the `(output message, message field)` it is copied to;
- `messages`: each output message's Basilisk type.

`make_fsw(name, inputs, initial_state, **params)` builds the binding's `AlgorithmModule`.
- `inputs` maps each role to a subscribed reader.
- `initial_state()` returns initial-state values by constructor parameter name, and is read at
  each `Reset`.
- `params` supplies the remaining constructor parameters, such as `mu` and the IMU mounting
  `dcm_PB`.

The module declares `period_s` (1 s), the period of the task the simulation runs it in, so the
flight software runs at 1 Hz on the simulation's dynamics step: 50 Hz at its `hi` fidelity and
20 Hz at `med` and `lo`. `Reset` builds the algorithm at the reset time and writes its initial
state. Each `UpdateState` after the reset time reads every input once, steps the algorithm and
writes its state. Each docstring gives what it refuses.

## Example: boot the dead reckoner against a simulated spacecraft

This example runs in a notebook or at a prompt, with the `sim` group installed
(`uv sync --group sim`). It builds WiseDynamics' `Leo500` scenario, which holds its IMU spacecraft
at its nominal configuration, and boots the dead reckoner on that vehicle. It then runs one minute,
the dynamics at the default fidelity's 20 Hz and the dead reckoner at 1 Hz, and compares the
estimate with the vehicle's truth:

```python
>>> import numpy as np
>>> from wise_dynamics.basilisk import ImuSpacecraft, Leo500
>>> from gnc_cdh.basilisk import make_fsw
>>> scenario = Leo500()
>>> vehicle = scenario.vehicle
>>> isinstance(vehicle, ImuSpacecraft)
True
>>> fsw = make_fsw(
...     "imu_dead_reckoning",
...     inputs=vehicle.readers(),
...     initial_state=scenario.initial_state,
...     dcm_PB=np.eye(3),
...     mu=Leo500.mu_m3_s2["earth"],
... )
>>> datasets = scenario.run(fsw, {}, duration_s=60.0)
>>> sorted(fsw.output_messages)
['nav_att', 'nav_trans']
>>> estimate = fsw.algorithm
>>> estimate.t
60.0
>>> truth_r_N, _ = datasets["truth/r_N"]
>>> bool(np.linalg.norm(estimate.r_N - truth_r_N[-1]) < 1.0)
True

```

`tests/sim/test_readme.py` runs this example.

## Adding an algorithm

1. Write the algorithm in `gnc_algorithms`. Its constructor takes `t0` and its initial state;
   it holds `t` and each output as an attribute; and `step(t=..., **inputs)` takes plain arrays by
   keyword and returns plain named arrays.
2. Add one `Binding` for it to `BINDINGS` in `gnc_cdh/basilisk/bindings.py`.
