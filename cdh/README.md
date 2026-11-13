# C&DH

`gnc_cdh` is the C&DH (command and data handling) partition. It hosts an algorithm from
`gnc_algorithms` in a simulator: `gnc_cdh.basilisk` hosts its Python build, and `gnc_cdh.fprime`
its F´ build.

The ground, `harness.ground.Ground`, flies a host that presents the link `gnc_cdh.link.Link`:
commands up, responses and every telemetry write down, in the form F´ uses. The ground runs the
scenario's procedure against it and records the flight. `AlgorithmModule` and the F´ host,
`FprimeModule`, each present it, so one procedure and one set of analyzers fly either build. The
link's docstrings say what each method does. Each host also has `build`, its build identity,
which the harness records in the flight's `flight.json`. The reasoning is in
[ADR 0004 rev 1](../docs/decisions/0004-carry-commands-and-telemetry-in-fprime-s-form-from-one-fpp-dictionary.md).

`gnc_cdh.basilisk` knows nothing about what any field means: it copies message fields to the
algorithm's `step` as plain arrays. Frames and mountings belong to the algorithm.

`gnc_cdh.basilisk.AlgorithmModule(algorithm, inputs, instance=..., dictionary=...)` hosts an
algorithm as the F´ instance `instance` would be hosted, held to `dictionary`, on a dict of
subscribed Basilisk readers, by role. The algorithm's names are its wiring:
- each keyword of its `step` other than `t` is a message field, read from the one input whose
  message has a field of that name;
- each command the dictionary gives the instance is a method of the algorithm, with exactly the
  command's parameters in order;
- `step` and each command handler return the telemetry they write, `{channel: value}`, or `None`.

Construction refuses a keyword that no input carries or that two do, and a command the algorithm
lacks or declares with other parameters.

A command arrives as F´'s bytes and is decoded with the dictionary's types, so a handler gets what
the F´ handler gets: an F32 as F32 holds it, an enum constant by name, an array as an array. It
runs at the next tick, before the step. A handler that returns answers `OK`; one that raises
`ValueError` answers `VALIDATION_ERROR`, and its message reaches the ground's `CommandFailed` and
command log as the reason; a packet the dictionary cannot decode gets the response F´'s dispatcher
gives it; any other exception is a bug and fails the case.

Each returned entry is one write, as an F´ component's `tlmWrite_<channel>` is. The module declares
`period_s` (1 s), so the flight software runs at 1 Hz, and the simulation steps its dynamics and
samples the IMU at that period at every fidelity. `AlgorithmModule`'s docstrings say how a tick
runs, how each write is checked and tagged, and what each method refuses.

## Example: fly the dead reckoner against a simulated spacecraft

This example runs in a notebook or at a prompt, with the `sim` group installed
(`uv sync --group sim`). It builds WiseDynamics' `Leo500` scenario, which holds its IMU spacecraft
at its nominal configuration, and boots the dead reckoner idle on that vehicle. A ground procedure
gives nav its state from tracking at t = 0, and the run lasts one minute, with the dynamics, the IMU
and the dead reckoner all stepping at 1 Hz. The ground's record is then compared with the
vehicle's truth:

```python
>>> import numpy as np
>>> from wise_dynamics.basilisk import ImuSpacecraft
>>> from wise_dynamics.basilisk.scenarios.leo500 import Leo500
>>> from gnc_algorithms.imu_dead_reckoning import dead_reckoner
>>> from harness.ground import Ground
>>> scenario = Leo500()
>>> isinstance(scenario.vehicle, ImuSpacecraft)
True
>>> fsw = dead_reckoner(scenario)
>>> async def procedure(ground):
...     truth = ground.truth()
...     await ground.send(
...         "nav.initNavState",
...         epoch=ground.now_s,
...         attitude=truth["q_BN"],
...         position=truth["r_N"],
...         velocity=truth["v_N"],
...     )
>>> ground = Ground(procedure, fsw, scenario.vehicle.tracking(), scenario.stop_ground)
>>> datasets = scenario.run(fsw, {}, duration_s=60.0, ground=ground)
>>> ground.command_log[0]["response"]
'OK'
>>> written = ground.telemetry_datasets()
>>> written["tlm/nav.navState"][0][:3].tolist()
['initialized', 'propagated', 'propagated']
>>> times = written["tlm_t/nav.bodyEciPos"][0]
>>> float(times[0]), float(times[-1]), len(times)
(1.0, 60.0, 60)
>>> truth_r_N, _ = datasets["truth/r_N"]
>>> bool(np.linalg.norm(written["tlm/nav.bodyEciPos"][0][-1] - truth_r_N[-1]) < 1.0)
True

```

`cdh/readme_test.py` runs this example.

## Adding an algorithm

Write the algorithm in `gnc_algorithms`, with its component model, `<Name>.fpp`, beside its
notebook: the commands and telemetry it implements, and no input ports. Its `step(t=..., **inputs)`
takes plain arrays by keyword, each named as the message field it reads; it has a method per
command; and both return the telemetry they write. Its builder hosts it with the dictionary
`Dictionary.from_component` generates from that model.

## The dictionary

`gnc_cdh.dictionary.Dictionary` reads an F´ JSON dictionary, F´'s published form of the FPP
model, and names its entries `<instance>.<entry>` with the deployment prefix dropped. It encodes
and decodes commands in F´'s packet format and channels in F´'s bytes. A channel's type is a
primitive, an enum or an array, such as `nav.bodyEciPos`, a `Gnc.Vector3`. `Channel.decode_many`
decodes a batch of writes as F´ serialized them, and `Channel.pack_many` packs a batch a Python
algorithm wrote into the same array; a written value that F´ would not pack into the channel's
type fails, naming the channel.

A role's shared entries are `.fppi` groups under `cdh/fprime/Interfaces/<Role>/`, which a
component's `.fpp` includes; the instance name is the role, so nav's entries are `nav.*` in every
build. A Python build's dictionary comes from FPP alone. `Dictionary.from_component(model,
component, instance=...)` instances the component alone and runs `fpp-to-dict` in a temporary
directory, against the F´ framework clone `just pinned` or `just local` fetches. Nothing is
compiled, nothing is written in the tree, and each content of the model is generated once per
process:

```python
>>> from pathlib import Path
>>> import gnc_algorithms.imu_dead_reckoning as reckoner
>>> from gnc_cdh.dictionary import Dictionary
>>> model = [Path(reckoner.__file__).with_name("ImuDeadReckoner.fpp")]
>>> nav = Dictionary.from_component(model, "Gnc.ImuDeadReckoner", instance="nav")
>>> position = nav.channel("nav.bodyEciPos")
>>> position.units
'm'
>>> position.pack_many([[6871.0e3, 0.0, 0.0], [6871.0e3, 1.0, 0.0]]).shape
(2, 3)

```

An F´ port's tests assert that its Python build's entries equal WiseFsw's, IDs aside, so the two
builds are held to one contract. The reasoning is in
[ADR 0004 rev 1](../docs/decisions/0004-carry-commands-and-telemetry-in-fprime-s-form-from-one-fpp-dictionary.md).

## The F´ host

`gnc_cdh.fprime.FprimeModule(imu, mu, dcm_PB)` runs the WiseFsw F´ deployment in the
simulation's process. The deployment's content is the dead reckoner, whose F´ component sits
beside its notebook, and the module's reset boots it idle with `mu` and the IMU's mounting.
`just fsw` builds the deployment into this package as the extension `_wise_fsw`, with the JSON
dictionary F´ generates for it alongside. `just pinned` and `just local` run it as part of their
sync, and `just test`, `just fly` and `just lab` run it first; a host built without it says to run
`just fsw`. The module takes `AlgorithmModule`'s `period_s`, so the two builds fly at one rate.

The deployment takes commands through F´'s own command dispatcher, which runs on the tick's
thread: `_wise_fsw.uplink(packet, context)` queues an F´ command packet, the next `step` runs it,
and `_wise_fsw.responses()` returns each response under its context. `_wise_fsw.telemetry()`
drains every telemetry write since the last call, each with its F´ time tag, and `boot` clears both
and leaves nav idle. The reasoning is in
[ADR 0004 rev 1](../docs/decisions/0004-carry-commands-and-telemetry-in-fprime-s-form-from-one-fpp-dictionary.md).

The module presents the link through these: `uplink` and `telemetry` pass through, `responses`
gives each response with no reason, since F´ gives none, and `values` decodes a channel's writes
through `gnc_cdh.dictionary` in one batch. An exception its reset or a tick raises is kept whole in
`failure`, as `AlgorithmModule` keeps one.
