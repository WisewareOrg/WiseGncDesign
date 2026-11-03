# C&DH

`gnc_cdh` is the C&DH (command and data handling) partition. It connects an algorithm from
`gnc_algorithms` to the messages of a host. It has two parts:
- a transport-neutral layer: the data dictionary, the frame transforms, and the protocols a hosted
  algorithm satisfies;
- one subpackage per transport. Each resolves the dictionary against that transport's messages and
  hosts the algorithm generically. `basilisk/` is the transport for the Basilisk simulator.

The parts stay apart:
- The data dictionary and the other modules directly under `gnc_cdh/` name no transport.
- A transport's generic modules (`__init__.py`, `algorithm_module.py`, `input_map.py`,
  `output_map.py`, `flight_software.py`) name no algorithm or sensor. A transport's `signals.py`
  is its one algorithm-specific table.
- Nothing under `cdh/` imports the simulation repository.

## Module map

| Module | Public surface |
| --- | --- |
Each class has its own module, named for it. `gnc_cdh` re-exports the neutral layer's public
names, and `gnc_cdh.basilisk` re-exports `AlgorithmModule`, `InputMap`, `OutputMap` and
`make_fsw`.

| Module | Public surface |
| --- | --- |
| `hosted_algorithm.py` | `HostedAlgorithm`: the protocol a hosted algorithm satisfies, and the hosting convention |
| `hosted_state.py` | `HostedState`: the protocol a hosted algorithm's state satisfies |
| `frames.py` | `platform_to_body`, `TRANSFORMS`: frame transforms by neutral name, and the mounting convention |
| `input_signal.py` | `InputSignal`: one sample field fed from one input role and signal |
| `output_signal.py` | `OutputSignal`: one state field published as one output role and signal |
| `algorithm_binding.py` | `AlgorithmBinding`: everything transport-neutral about hosting one algorithm |
| `data_dictionary.py` | `BINDINGS`, `binding(name)`: the dictionary's entries |
| `basilisk/input_field.py` | `InputField`: where a Basilisk reader carries one input signal |
| `basilisk/output_field.py` | `OutputField`: where a Basilisk message carries one output signal |
| `basilisk/signals.py` | `INPUT_SIGNALS`, `OUTPUT_SIGNALS`: each (role, signal) resolved to a Basilisk message and payload field |
| `basilisk/input_map.py` | `InputMap`: one payload field read into one sample field |
| `basilisk/output_map.py` | `OutputMap`: one state field written to one payload field |
| `basilisk/algorithm_module.py` | `AlgorithmModule`: the generic Basilisk host module |
| `basilisk/flight_software.py` | `make_fsw`: builds a named algorithm's `AlgorithmModule` from the dictionary |

## The data dictionary

A binding names five things:
- an algorithm class;
- its sample type;
- for each sample field, the input role and signal that feeds it;
- for each published state field, the output role and signal it feeds;
- for each input, an optional frame transform.

A role is a port, such as one sensor. A signal is the quantity carried on it.

| Role | Signal | Direction | Units | Frame |
| --- | --- | --- | --- | --- |
| `imu` | `angular_rate` | input | rad/s | the IMU's platform frame P, transformed `platform_to_body` |
| `imu` | `specific_force` | input | m/s^2 (non-gravitational) | P, transformed `platform_to_body` |
| `navigation` | `sigma_BN` | output | MRP | B with respect to N |
| `navigation` | `r_N` | output | m | inertial |
| `navigation` | `v_N` | output | m/s | inertial |

| Binding | Algorithm | Inputs | Outputs |
| --- | --- | --- | --- |
| `imu_dead_reckoning` | `ImuDeadReckoner` | `imu`: `angular_rate` → `omega_B`, `specific_force` → `accel_B` | `navigation`: `sigma_BN`, `r_N`, `v_N` |

`AlgorithmBinding.init_keys` lists the constructor parameters a host must supply, read from the
constructor's signature: every parameter other than `t0` that has no default. `build(t0, init)`
constructs the algorithm with keyword arguments.

## Mountings

A mounting is the DCM [PB] from the body frame B to a sensor's platform frame P, with
v_P = [PB] v_B. `gnc_cdh.frames.platform_to_body` is the one statement of the transform.

A host supplies a mounting for every role that carries a framed signal. An identity mounting is
passed as `np.eye(3)`. It is never assumed.

## The Basilisk transport

**Signals.** `basilisk/signals.py` resolves each (role, signal):

| (role, signal) | Basilisk | Payload field |
| --- | --- | --- |
| (`imu`, `angular_rate`) | `IMUSensorMsgReader` | `AngVelPlatform` |
| (`imu`, `specific_force`) | `IMUSensorMsgReader` | `AccelPlatform` |
| (`navigation`, `sigma_BN`) | `NavAttMsg`, output `nav_att` | `sigma_BN` |
| (`navigation`, `r_N`) | `NavTransMsg`, output `nav_trans` | `r_BN_N` |
| (`navigation`, `v_N`) | `NavTransMsg`, output `nav_trans` | `v_BN_N` |

**The host module.** `AlgorithmModule` is a Basilisk `SysModel`. Its lifecycle:
- `Reset` builds the algorithm at the reset time from `init_from()` and writes the initial state to
  every output message.
- Each later `UpdateState` reads every input once. It applies each input map's transform, builds
  one sample with `t` in s, steps the algorithm, and writes the new state.
- The `UpdateState` call at the reset time itself leaves the state as built.

It refuses five things:
- maps naming an unknown input, output, payload field or sample field, at construction;
- a sample field fed twice or left unfed, at construction;
- an unsubscribed input, at `Reset`;
- a state lacking a mapped field, at `Reset`;
- an input never written, at a step.

`output_messages` holds its output messages by name, ready to record.

**`make_fsw`.**

```python
make_fsw(name, inputs, initial_state, mountings=None, **params) -> AlgorithmModule
```

It builds the host module for the binding `name`:
- `inputs` maps each role to a subscribed reader;
- `initial_state()` returns the initial state by constructor parameter name, and is read at each
  `Reset`;
- `mountings` maps each framed role to its [PB];
- `params` supplies the remaining constructor parameters, such as `mu`.

The function refuses these, each by name:
- an unknown binding;
- a missing or wrongly typed reader;
- a missing or stray mounting, or one that is not a proper rotation;
- an unknown parameter;
- a key supplied by both `initial_state()` and `params`.

## Example: boot the dead reckoner against a plant

This example runs in a notebook or at a prompt, with the `sim` group installed
(`uv sync --group sim`). It builds WiseDynamics' IMU spacecraft at its nominal configuration and
boots the dead reckoner on it. It then runs one minute, and compares the estimate with the plant's
truth:

```python
>>> import numpy as np
>>> from wise_dynamics.basilisk import ImuSpacecraft, run_case
>>> from gnc_cdh.basilisk import make_fsw
>>> plant = ImuSpacecraft()
>>> fsw = make_fsw(
...     "imu_dead_reckoning",
...     inputs=plant.readers(),
...     initial_state=plant.initial_state,
...     mountings={"imu": np.eye(3)},
...     mu=plant.mu,
... )
>>> recording = run_case(plant, fsw, fsw_outputs=fsw.output_messages, duration_s=60.0)
>>> sorted(fsw.output_messages)
['nav_att', 'nav_trans']
>>> estimate = fsw.algorithm.state
>>> estimate.t
60.0
>>> truth_r_N = np.array(recording["truth"].r_BN_N[-1])
>>> bool(np.linalg.norm(estimate.r_N - truth_r_N) < 1.0)
True

```

`tests/sim/test_readme.py` runs this example.

## Adding an algorithm

1. Add an `AlgorithmBinding` to `BINDINGS` in `data_dictionary.py`, with one `InputSignal` per
   sample field and one `OutputSignal` per published state field.
2. Reuse a signal where the quantity is the same. A new signal gets a row in the dictionary table
   above.
3. Give every new (role, signal) a row in `basilisk/signals.py`.

`tests/cdh/test_bindings.py` builds every binding against real Basilisk readers.

## Adding a transport

A transport is a sibling of `basilisk/` holding three modules:
- its own resolution table;
- a generic host module;
- a `make_fsw`.

Its `__init__.py`, generic host module, map modules and `make_fsw` module name no algorithm or
sensor.
