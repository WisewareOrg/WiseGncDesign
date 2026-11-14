# Flight software

`fsw` is the flight software. An algorithm from `algorithms` is hosted in a simulator by
`fsw.python`, its Python build, or by `lab`, its F´ build.

The ground, `ground.procedures.Ground`, runs the scenario's procedure against either build's
radio edge and records the flight; [RadioEdge](#radioedge) says which host presents it.

`fsw.python` knows nothing about what any field means: it copies message fields to the
algorithm's `step` as plain arrays. Frames and mountings belong to the algorithm.

`fsw.python.AlgorithmModule(algorithm, inputs, instance=..., dictionary=...)` hosts an
algorithm as the F´ instance `instance` would be hosted, held to `dictionary`, on a dict of
subscribed Basilisk readers, by role. Its docstrings say how the algorithm's names wire it to its
inputs, commands and telemetry, how a tick runs, and what it refuses. It declares `period_s`
(1 s), so the flight software runs at 1 Hz, and the simulation steps its dynamics and samples the
IMU at that period at every fidelity.

## RadioEdge

`ground.radio_edge.RadioEdge` is the flight software as the ground sees it, in F´'s names and
values on either build, so one procedure and one set of analyzers fly either build. Its docstrings
say what crosses it.

`AlgorithmModule` presents the radio edge itself, dispatching each command by name to the
algorithm's method of that name. The F´ host, `FprimeModule`, presents it through the F´ ground
station, `ground.fprime_station.FprimeStation`, the only F´ codec in the repository and the part
F´'s real ground data system replaces: F´ packets exist only between it and `_wise_fsw`.

Each host also has `build`, its build identity, which the harness records in the flight's
`flight.json`. How commands and telemetry travel between the ground and each build, and why every
write is pushed rather than sampled, is in
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).

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
>>> from algorithms.imu_dead_reckoning import dead_reckoner
>>> from ground.procedures import Ground
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

`fsw/readme_test.py` runs this example.

## Adding an algorithm

Write the algorithm in `algorithms`, with its component model, `<Name>.fpp`, beside its
notebook: the ports its GNC sub-topology wires, and the commands and telemetry it implements. Its
`step(t=..., **inputs)` takes plain arrays by keyword, each named as the message field it reads; it
has a method per command; and both return the telemetry they write. Its builder hosts it with the
dictionary `Dictionary.from_component` generates from that model.

## The dictionary

`ground.dictionary.Dictionary` reads an F´ JSON dictionary, F´'s published form of the FPP
model, and names its entries `<instance>.<entry>` with the instance's module dropped. It holds
values to the model's types and leaves the bytes to the F´ ground station. `Dictionary.arguments`
holds a command's arguments to its parameters' types. A channel's type is a primitive, an enum or
an array, such as `nav.bodyEciPos`, a `Gnc.Vector3`. `Channel.pack_many` packs a batch a Python
algorithm wrote into the array the station decodes F´'s writes into; a written value that F´ would
not pack into the channel's type fails, naming the channel.

A role's shared entries are `.fppi` groups under `fsw/fpp/interfaces/<Role>/`, which a
component's `.fpp` includes; the instance name is the role, so nav's entries are `nav.*` in every
build. A Python build's dictionary comes from FPP alone. `Dictionary.from_component(model,
component, instance=...)` instances the component alone and runs `fpp-to-dict` in a temporary
directory, against the F´ framework clone `just pinned` or `just local` fetches. Nothing is
compiled, nothing is written in the tree, and each content of the model is generated once per
process:

```python
>>> from pathlib import Path
>>> import algorithms.imu_dead_reckoning as reckoner
>>> from ground.dictionary import Dictionary
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
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).

The bus structs are in `fsw/fpp/interfaces/Bus.fpp`, and `bus_test.py` beside it holds each to its
Basilisk message. The reasoning is in
[ADR 0003 rev 3](../docs/decisions/0003-fly-the-fprime-flight-software-inside-the-basilisk-process.md).

## The FPP model

`fsw.codegen.fpp_model` is the one module that reads FPP's model in Python: `read(files)` runs
the native `fpp` binary inside the `fprime_fpp` package, `fpp to-json`, into a temporary directory,
and returns a `Model` of named tuples by qualified name: instances with their base IDs, each
topology's connections with both port numbers resolved, numeric constants, struct, enum and array
types, each component's commands, channels, parameters and general output ports with the file
that defines it, and annotations. It needs no compiler,
no Java and no F´ build, only the model's `.fpp` files, F´'s framework files among them from the
clone `just pinned` or `just local` fetches. `to-json`'s output is unversioned compiler internals,
so a key the module reads that is missing raises `KeyError`. The reasoning is in
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).

## FPP types in Python

`fsw.codegen.fpp_types` is FPP's types as named tuples, generated when it is imported and never
written in the tree, with `converter` between them. Its docstrings say what each FPP type becomes,
which tuples an algorithm's component gets, and how fields are converted:

```python
>>> from Basilisk.architecture import messaging
>>> from fsw.codegen.fpp_types import Bus, Gnc, converter
>>> payload = messaging.IMUSensorMsgPayload()
>>> payload.AngVelPlatform = [0.0, 0.0, 1.0e-3]
>>> bus = converter(messaging.IMUSensorMsgPayload, Bus.ImuSensorMsg)(payload)
>>> reading = converter(Bus.ImuSensorMsg, Gnc.ImuReading)(bus)
>>> reading.angVelPlatform.tolist()
[0.0, 0.0, 0.001]
>>> Gnc.ImuDeadReckonerTelemetry(navState="initialized").bodyEciPos is None
True

```

The reasoning is in
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).

## The F´ host

`lab.FprimeModule(imu, mu, dcm_PB)` runs the WiseFsw F´ deployment in the
simulation's process. The deployment's content is the dead reckoner, whose F´ component sits
beside its notebook, and the module's reset boots it idle with `mu` and the IMU's mounting.
`just fsw` builds the deployment into `lab` as the extension `_wise_fsw`, with the JSON
dictionary F´ generates for it alongside. `just pinned` and `just local` run it as part of their
sync, and `just test`, `just fly` and `just lab` run it first; a host built without it says to run
`just fsw`. The module takes `AlgorithmModule`'s `period_s`, so the two builds fly at one rate.

The dead reckoner's GNC sub-topology, `fsw/fpp/gnc/ImuDeadReckoning.fpp`, holds nav, the F´ rate
group that runs it, the rate-group driver, and its rate as the FPP constant `navDivider`; `phase`
blocks on the driver and the rate group pass the constant to their `configure()`. Each GNC
sub-topology exposes the ports `tickIn`, `imuIn` and `navConfigIn`, which the deployment wires.
Each configuration's deployment, `WiseFsw.<Cfg>Fsw`, is rendered at build time from the templates
in `fsw/fprime/deployment/`, one per file in `fsw/fpp/gnc/`, into the build directory, where it
compiles its GNC sub-topology with it; the shared instances are in
`fsw/fprime/deployment/instances.fpp`. The F´ build takes every directory under `algorithms/` with
a `CMakeLists.txt`, and F´ finds which algorithms a configuration links from its FPP. Each `step`
sets SimTime to the simulation's time, then SimTime ticks the driver once, so nav runs on every
`navDivider`-th step.

The rate group's health telemetry is recorded with every other channel; the deployment links F´'s
stub `Os::RawTime`, so its cycle times read 0. A process's first case reproduces its rate-group
datasets from the seed; a later case carries the rate group's `CycleCount` over from the cases
before it and lacks the channels written only on change. Issue 59 Power-cycle the F´ build per case
closes that gap. Nav's datasets reproduce bitwise in every case.

`fsw.codegen.deployment.fpp_files(configuration, directory)` renders a configuration's topology
and lists its deployment's FPP files, the algorithms the F´ build takes among them, for
`fpp_model.read`. The reasoning is in
[ADR 0003 rev 3](../docs/decisions/0003-fly-the-fprime-flight-software-inside-the-basilisk-process.md)
and [ADR 0005 rev 1](../docs/decisions/0005-partition-each-build-into-rio-cdh-gnc-and-platform-one-frame-per-tick.md).

The deployment takes commands through F´'s own command dispatcher, which runs on the tick's
thread: `_wise_fsw.uplink(packet, context)` queues an F´ command packet, the next `step` runs it,
and `_wise_fsw.responses()` returns each response under its context. `_wise_fsw.telemetry()`
drains every telemetry write since the last call, each with its F´ time tag, and `boot` runs the
commands left queued, clears GroundLink's held responses and writes, and leaves nav idle. The
module's radio edge is an `FprimeStation` on these pins. The reasoning is in
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).
