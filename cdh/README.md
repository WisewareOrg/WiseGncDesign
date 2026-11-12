# C&DH

`gnc_cdh` is the C&DH (command and data handling) partition. It hosts an algorithm from
`gnc_algorithms` in a simulator: `gnc_cdh.basilisk` hosts its Python build, and `gnc_cdh.fprime`
its F´ build.

Each host implements `fly(run) -> datasets`, which the harness calls to fly a case and record the
estimate, and `build`, the host's build identity, which the harness records in the flight's
`flight.json`. The contract and its reasoning are in
[ADR 0003 rev 1](../docs/decisions/0003-fly-the-fprime-flight-software-inside-the-basilisk-process.md).

`gnc_cdh.basilisk` knows nothing about what any field means: it copies message fields to the
algorithm's `step` as plain arrays, and the arrays it returns into messages, by name. Frames,
mountings and units belong to the algorithm.

`gnc_cdh.basilisk.AlgorithmModule(algorithm, inputs)` hosts an algorithm built at the simulation's
start time on a dict of subscribed Basilisk readers, by role. The algorithm's names are its wiring:
- each keyword of its `step` other than `t` is a message field, read from the one input whose
  message has a field of that name;
- its outputs are its public attributes other than `t`, each named in Basilisk's navigation
  convention and written to the standard message that carries a field of that name.

`STANDARD_MESSAGES` is the host's one table of those messages: `nav_att`, a `NavAttMsg` carrying
`sigma_BN` and `omega_BN_B`, and `nav_trans`, a `NavTransMsg` carrying `r_BN_N` and `v_BN_N`.
Construction refuses a keyword that no input carries or that two do, and an output no standard
message carries.

The module declares `period_s` (1 s), the period of the task the simulation runs it in, so the
flight software runs at 1 Hz on the simulation's dynamics step: 50 Hz at its `hi` fidelity,
20 Hz at `med` and 10 Hz at `lo`. `Reset` writes the algorithm's outputs as it holds them. Each
`UpdateState` after the algorithm's `t` reads every input once, steps the algorithm and writes what
it returns. Each docstring gives what it refuses.

## Example: boot the dead reckoner against a simulated spacecraft

This example runs in a notebook or at a prompt, with the `sim` group installed
(`uv sync --group sim`). It builds WiseDynamics' `Leo500` scenario, which holds its IMU spacecraft
at its nominal configuration, and boots the dead reckoner on that vehicle. It then runs one minute,
the dynamics at the default fidelity's 10 Hz and the dead reckoner at 1 Hz, and compares the
estimate with the vehicle's truth:

```python
>>> import numpy as np
>>> from wise_dynamics.basilisk import ImuSpacecraft
>>> from wise_dynamics.basilisk.scenarios.leo500 import Leo500
>>> from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner
>>> from gnc_cdh.basilisk import AlgorithmModule
>>> scenario = Leo500()
>>> vehicle = scenario.vehicle
>>> isinstance(vehicle, ImuSpacecraft)
True
>>> initial = scenario.initial_state()
>>> algorithm = ImuDeadReckoner(
...     initial["sigma0_BN"],
...     initial["r0_N"],
...     initial["v0_N"],
...     t0=0.0,
...     mu=Leo500.mu_m3_s2["earth"],
...     dcm_PB=np.eye(3),
... )
>>> fsw = AlgorithmModule(algorithm, vehicle.readers())
>>> sorted(fsw.output_messages)
['nav_att', 'nav_trans']
>>> datasets = scenario.run(fsw, {}, duration_s=60.0)
>>> fsw.algorithm.t
60.0
>>> truth_r_N, _ = datasets["truth/r_N"]
>>> bool(np.linalg.norm(fsw.algorithm.r_BN_N - truth_r_N[-1]) < 1.0)
True

```

`cdh/readme_test.py` runs this example.

## Adding an algorithm

Write the algorithm in `gnc_algorithms`. Its `step(t=..., **inputs)` takes plain arrays by keyword,
each named as the message field it reads, and returns plain named arrays; it holds `t` and each
output as an attribute, named in Basilisk's navigation convention. An output that no entry of
`STANDARD_MESSAGES` carries gets that message added there.

## The F´ host

`gnc_cdh.fprime.FprimeModule(imu, mu, dcm_PB, initial)` runs the WiseFsw F´ deployment in the
simulation's process. The deployment's content is the dead reckoner, whose F´ component sits beside
its notebook. `just fsw` builds the deployment into this package as the extension `_wise_fsw`, with
the JSON dictionary F´ generates for it alongside. `just pinned` and `just local` run it as part of
their sync, and `just test`, `just fly` and `just lab` run it first. The module takes
`AlgorithmModule`'s `period_s`, so the two builds fly at one rate.

`gnc_cdh.fprime` decodes every telemetry channel generically from F´'s generated dictionary, so the
C&DH and the ground learn fields through the dictionary. The one piece specific to an algorithm is
small and named: the dead reckoner's channel-to-estimate mapping, in
`FprimeModule.estimate_datasets`. It becomes configuration once the shared dictionary is designed.
The reasoning is in
[ADR 0003 rev 1](../docs/decisions/0003-fly-the-fprime-flight-software-inside-the-basilisk-process.md).
