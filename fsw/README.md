# Flight software

`fsw` is the flight software. A configuration, a GNC sub-topology of algorithms from
`algorithms`, flies in a simulator as `fsw.python`, its Python build, or as `lab`, its F´ build.

The ground, `ground.procedures.Ground`, runs the scenario's procedure against either build's
radio edge and records the flight; [RadioEdge](#radioedge) says which build presents it.

## The Python build

`fsw.python.FrameRunner(configuration, prm_path, components)` is a configuration's Python build,
the build WiseDynamics' `FswHost` hosts: the harness flies `FswHost(build, vehicle)`, which boots
it at reset and ticks it every `period_s` with each role's Basilisk message. `components` are the
algorithms' classes, each named as its FPP component. A keyword-only `contract`, a
`fsw.codegen.deployment.Contract` of algorithm `.fpp` files and a directory of GNC sub-topologies,
defaults to the repository's, `CONTRACT`; a test flies a mock contract through it, and
`fsw.codegen.fpp_types.load(contract)` generates that contract's tuples beside the repository's.
Each tick is one frame through the partitions
of [ADR 0005 rev 1](../docs/decisions/0005-partition-each-build-into-rio-cdh-gnc-and-platform-one-frame-per-tick.md),
in `fsw/python/<partition>/`, and FPP gives each its structure:

- **platform** runs the frame. Its `period_s` is the sub-topology's base tick, the FPP constant
  `tickPeriod`, which `fsw.codegen.deployment.tick_period` reads, and `platform.rates` runs each
  rate group `<stem>RateGroup` every `<stem>Divider`-th tick, counting ticks as F´'s
  `Svc.RateGroupDriver` does.
- **RIO** reads each sensor role's message as its bus struct, copying it within the tick, and
  returns the actuator commands: for each actuator role GNC wrote in the frame, a fresh
  `messaging.<Name>Payload` of the message its bus struct mirrors; a role GNC did not write is
  absent, and keeps its last command on the vehicle.
- **CDH** dispatches each command by name to its algorithm's method of that name, with F´'s
  responses, converts each sensor role's bus struct to its GNC input and each actuator role's GNC
  output to its bus struct, logs every telemetry write tagged with the tick's time, and reads each
  algorithm's parameters from the case's record at boot. Its `GroundLink` holds what the ground
  uplinks and drains, and the frame runner presents the radio edge through it.
  `Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp` pairs each role, as its annotation states, and
  a configuration takes the roles its sub-topology exposes (`fsw.codegen.roles.taken`).
- **GNC** runs the sub-topology's algorithms in its rate groups' order, routing each output to the
  input it is wired to, and returns what its members wrote on the sub-topology's output ports.

Each module's docstrings say what it refuses. An algorithm's `step(t, ...)` takes a keyword per
data input, named as the input port without its `In`, in the input's FPP type, and returns its
`<Name>Outputs` and `<Name>Telemetry` tuples; its command methods return its `<Name>Telemetry` or
`None`. Frames and mountings belong to the algorithm.

## RadioEdge

`ground.radio_edge.RadioEdge` is the flight software as the ground sees it, in F´'s names and
values on either build, so one procedure and one set of analyzers fly either build. Its docstrings
say what crosses it.

The Python build presents the radio edge itself, through its CDH. The F´ build presents it through
the F´ ground station, `ground.fprime_station.FprimeStation`, on the lab adapter's pins: the only
F´ codec in the repository and the part F´'s real ground data system replaces. F´ packets exist
only between it and the configuration's extension, `_wise_fsw_<configuration>`.

Each build also has `build`, its build identity, which the harness records in the flight's
`flight.json`, as
[ADR 0003 rev 3](../docs/decisions/0003-fly-the-fprime-flight-software-inside-the-basilisk-process.md)
records. How commands and telemetry travel between the ground and each build, and why every
write is pushed rather than sampled, is in
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).

## Example: fly the dead reckoner against a simulated spacecraft

This example runs in a notebook or at a prompt, with the `sim` group installed
(`uv sync --group sim`). It builds WiseDynamics' `Leo500` scenario, which holds its IMU spacecraft
at its nominal configuration, writes the case's parameter record from the notebook's
`parameters(scenario)` under nav's qualified instance, as the harness does beside each run file,
and boots the `ImuDeadReckoning` configuration's Python build idle with the values it reads back
from the record, hosted on that vehicle by WiseDynamics' `FswHost` as the harness hosts it. A
ground procedure gives nav its state from tracking at t = 0, and the run lasts one minute, with the
dynamics, the IMU and the dead reckoner all stepping at 1 Hz. The ground's record is then compared
with the vehicle's truth:

```python
>>> import tempfile
>>> from pathlib import Path
>>> import numpy as np
>>> from wise_dynamics.basilisk import FswHost, ImuSpacecraft
>>> from wise_dynamics.basilisk.scenarios.leo500 import Leo500
>>> from algorithms.imu_dead_reckoning import ImuDeadReckoner, parameters
>>> from fsw.python import FrameRunner
>>> from ground.parameters import write
>>> from ground.procedures import Ground
>>> scenario = Leo500()
>>> isinstance(scenario.vehicle, ImuSpacecraft)
True
>>> case = tempfile.TemporaryDirectory()
>>> path = Path(case.name) / "run_0000.prm.json"
>>> record = write({"ImuDeadReckoning.nav": parameters(scenario)}, path)
>>> fsw = FrameRunner("ImuDeadReckoning", record, (ImuDeadReckoner,))
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
>>> datasets = scenario.run(FswHost(fsw, scenario.vehicle), {}, duration_s=60.0, ground=ground)
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
>>> case.cleanup()

```

`fsw/readme_test.py` runs this example.

## Adding an algorithm

Write the algorithm as the package `algorithms/<folder>/`, with its `__init__.py` and its component
model, `<Name>.fpp`, beside its notebook, `<folder>.py`: the ports its GNC sub-topology wires, the
commands and telemetry it implements, its parameters, and an `@ provides: SYS...` line per
capability it claims. Its class, in the notebook, is named as the component and takes its
`<Name>Parameters`; its `step` and command methods are as [the Python build](#the-python-build)
says. Its notebook's `parameters(scenario)` gives its `<Name>Parameters` tuple for a case, which
the ground writes as the case's record, keyed by the algorithm's instance in its GNC sub-topology;
a component without parameters needs none. A mission flies a configuration by name,
`Mission(gnc=…, build=…)`, and finds the class and `parameters` in the notebook by the
component's name, importing the notebook as `algorithms.<folder>.<folder>`.

## The dictionary

`fsw.codegen.dictionary.Dictionary` reads an F´ JSON dictionary, F´'s published form of the FPP
model, and names its entries `<instance>.<entry>` with the instance's module dropped. It holds
values to the model's types and leaves the bytes to the F´ ground station. `Dictionary.arguments`
holds a command's arguments to its parameters' types. A channel's type is a primitive, an enum or
an array, such as `nav.bodyEciPos`, a `Gnc.Vector3`. `Channel.pack_many` packs a batch a Python
algorithm wrote into the array the station decodes F´'s writes into; a written value that F´ would
not pack into the channel's type fails, naming the channel.

A role's shared entries are `.fppi` groups under `fsw/fpp/interfaces/<Role>/`, which a
component's `.fpp` includes; the instance name is the role, so nav's entries are `nav.*` in every
build. A Python build's dictionary comes from FPP alone:
`Dictionary.from_sub_topology(configuration)` generates the configuration's, a deployment
importing its GNC sub-topology, its rate groups' entries beside its algorithms', run through
`fpp-to-dict` in a temporary directory against the F´ framework clone `just pinned` or `just local`
fetches. Nothing is compiled, nothing is written in the tree, and each content of the model is
generated once per process. `Dictionary.from_component(model, instance)` generates one
component's alike, instanced alone, for mocks and tests:

```python
>>> from fsw.codegen.dictionary import Dictionary
>>> dictionary = Dictionary.from_sub_topology("ImuDeadReckoning")
>>> position = dictionary.channel("nav.bodyEciPos")
>>> position.units
'm'
>>> position.pack_many([[6871.0e3, 0.0, 0.0], [6871.0e3, 1.0, 0.0]]).shape
(2, 3)

```

`fsw/codegen/dictionary_test.py` asserts that every algorithm's GNC instance, in its configuration's
generated dictionary, has WiseFsw's entries, IDs aside, and WiseFsw's parameter IDs, so the two
builds are held to one contract. The reasoning is in
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).

The bus structs are in `fsw/fpp/interfaces/Bus.fpp`, and `bus_test.py` beside it holds each to its
Basilisk message. The reasoning is in
[ADR 0006 rev 1](../docs/decisions/0006-meet-the-sim-as-a-hardware-in-the-loop-rig-on-bus-bytes.md).

## The FPP model

`fsw.codegen.fpp_model` is the one module that reads FPP's model in Python: `read(files)` runs
the native `fpp` binary inside the `fprime_fpp` package, `fpp to-json`, into a temporary directory,
and returns a `Model` of named tuples by qualified name: instances with their base IDs, each
topology's connections with both port numbers resolved, the instance port each topology port
exposes, numeric constants, struct, enum and array types, each component's commands, channels,
parameters and general output and input ports with the file that defines it, and annotations. It
needs no compiler, no Java and no F´ build, only the model's `.fpp` files, F´'s framework files
among them from the clone `just pinned` or `just local` fetches. `to-json`'s output is unversioned
compiler internals, so a key the module reads that is missing raises `KeyError`. The reasoning is in
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

## The lab adapter

`lab.Adapter(configuration, prm_path, *, contract=CONTRACT)` is a configuration's WiseFsw F´
deployment as a WiseDynamics FSW build, which `FswHost` hosts in the simulation's process, with the
parameters of the case's record at `prm_path`. `just fsw` builds the deployment of each
configuration `fsw.codegen.deployment.fprime_configurations` selects, of the repository's contract
and the test mocks', into `lab` as the extension `_wise_fsw_<configuration>`, with the JSON
dictionary F´ generates for it alongside, `lab.dictionary_path(configuration)`; its CMake target
`_wise_fsw` builds them all.
`just pinned` and `just local` run it as part of their sync, and `just test`, `just fly` and
`just lab` run it first; an adapter built without it says to run `just fsw`. The adapter's
`period_s` is the configuration's `tickPeriod`, the Python build's, so the two builds fly at one
rate.

The adapter's `boot` power-cycles the deployment, as a vehicle is power-cycled between flights:
`lab.power_cycle.power_cycle(configuration)`, the one entry point to the extensions, loads a fresh
copy of the configuration's, and the copy's `boot` sets its topology up and leaves every component
idle. Booting, F´'s stock PrmDb loads the case's `.dat`, which `ground.parameters.dat` makes beside
the record with F´'s own `fprime-prm-write` conversion, in-process, when the adapter is
constructed. PrmDb's sandbox is that directory, never the root, and a parameter the load leaves
invalid fails the boot, named by its ID. A copy boots once, and an F´ assert raises `RuntimeError`
in Python with F´'s own text. `FswHost` keeps whatever `boot` or `tick` raises, and checks the
vehicle's readers; the adapter refuses a tick that is not a whole microsecond, which F´'s clock
cannot hold.

The dead reckoner's GNC sub-topology, `fsw/fpp/gnc/ImuDeadReckoning.fpp`, holds nav, the F´ rate
group that runs it, the rate-group driver, and its rate as the FPP constant `navDivider`; `phase`
blocks on the driver and the rate group pass the constant to their `configure()`. Each GNC
sub-topology exposes the port `tickIn`, and a port per role it takes: `<role>In` for a sensor,
`<role>Out` for an actuator.
Each configuration's deployment, `WiseFsw.<Cfg>Fsw`, is rendered at configure time by
`python -m fsw.codegen.deployment` from `fsw/fprime/deployment/Fsw.fpp.in`, its role wiring
generated, and the other templates in `fsw/fprime/deployment/` by CMake, into the build directory,
where it compiles its GNC sub-topology with it; the shared instances are in
`fsw/fprime/deployment/instances.fpp`. The F´ build builds the configurations
`fsw.codegen.deployment.fprime_configurations` selects, those whose every member's component has an
F´ component: its `.fpp` sits beside a `CMakeLists.txt`, as in every directory under `algorithms/`
the F´ build takes, and in `fsw/mock/actuator/`, the test mock flown by `MockActuation`. F´ finds
which algorithms a configuration links from its FPP. Each `_wise_fsw_<configuration>.step(t_ns,
bus)` sets SimTime to the simulation's time, runs the queued commands, pushes each `(port, bytes)`
of `bus` out on LabBusDriver's serial port `busOut[port]`, then SimTime ticks the rate-group driver
once, so nav runs on every `navDivider`-th step, and returns each `(port, bytes)` the step's GNC
sent LabBusDriver's serial port `busIn[port]`. LabBusDriver is the RIO bus driver the lab uses: the
typed port each `busOut` connects to deserializes the bytes as F´ serializes the bus struct, and
bytes it does not consume exactly trip F´'s assert; each `busIn` holds the bytes of the bus struct
its typed port sends until the step drains them. The template's role wiring is generated from the
roles the sub-topology exposes: the k-th sensor role's `labBusDriver.busOut[k] -> cdh.<role>In` and
`cdh.<role>Out` to the sub-topology's `<role>In`, and the k-th actuator role's sub-topology
`<role>Out` to `cdh.<role>In` and `cdh.<role>Out -> labBusDriver.busIn[k]`, where `cdh` is the
generated `Cdh.BusConverter`; an added sensor or actuator is FPP declarations alone. Each tick, the
adapter pushes each sensor role's message, as `lab.bus_emulator` writes it, on the port
`fsw.codegen.deployment.bus_port(configuration, "<role>In")` reads back from the rendered
deployment; a tick missing one names it. It returns, for each actuator role's bytes the step
returned, the Basilisk message `lab.bus_emulator.deserialize` reads them back as.

The rate group's health telemetry is recorded with every other channel; the deployment links F´'s
stub `Os::RawTime`, so its cycle times read 0. Each case flies a fresh copy of the deployment, so
every case reproduces its rate-group datasets from the seed, as it does nav's.

`fsw.codegen.deployment.fpp_files(configuration, directory, *, contract=CONTRACT)` renders a
configuration's topology and lists its deployment's FPP files, every algorithm's among them, for
`fpp_model.read`. The reasoning is on
[issue 57 GNC sub-topology](https://github.com/WisewareOrg/WiseGncDesign/issues/57) and in
[ADR 0003 rev 3](../docs/decisions/0003-fly-the-fprime-flight-software-inside-the-basilisk-process.md)
and [ADR 0005 rev 1](../docs/decisions/0005-partition-each-build-into-rio-cdh-gnc-and-platform-one-frame-per-tick.md).

The F´ build's CDH component, `Cdh.BusConverter`, is generated from its declaration in
`fsw/fpp/interfaces/Cdh.fpp` by `fsw.codegen.bus_converter` while `just fsw` builds, into the build
directory: for each role `fsw.codegen.roles` reads, an inline conversion `convert_<role>` that
builds the struct its `<role>Out` sends from the one its `<role>In` takes, by the field rule the
Python build's converter follows, `fsw.codegen.fields`: a sensor's GNC struct from its bus struct,
an actuator's bus struct from its GNC struct. A handler sends the result on `<role>Out`. Each
deployment instances it as `cdh`, between LabBusDriver and the GNC. The generator emits two test
pins into each extension: `bus_<Struct>(<member>=...)` returns F´'s serialization of a bus struct
built from its members' values, and `cdh_<role>(bus_bytes)` for a sensor, `cdh_<role>(icd_bytes)`
for an actuator, returns F´'s serialization of the struct the conversion makes from the one F´
deserializes from the bytes. `lab.bus_emulator.serialize(message)` writes a Basilisk message as
the bytes F´ serializes its bus struct to, and `lab.bus_emulator.deserialize(bus, data)` reads an
actuator's bytes back into its Basilisk message, both built from `fsw/fpp/interfaces/Bus.fpp` at
import; each is held to `bus_<Struct>`'s bytes. A bus or GNC field must be an array of one of
`fsw.codegen.fields.STRUCT_CODES`' primitives; the generator and the emulator refuse anything else,
naming it. The reasoning is in
[ADR 0005 rev 1](../docs/decisions/0005-partition-each-build-into-rio-cdh-gnc-and-platform-one-frame-per-tick.md)
and [ADR 0006 rev 1](../docs/decisions/0006-meet-the-sim-as-a-hardware-in-the-loop-rig-on-bus-bytes.md).

The deployment takes commands through F´'s own command dispatcher, which runs on the tick's
thread: `uplink(packet, context)` queues an F´ command packet, the next `step` runs it, and
`responses()` returns each response under its context. `telemetry()` drains every telemetry write
since the last call, each with its F´ time tag. The adapter carries these pins in bytes: `uplink`
and `responses` reach the current copy, and its `telemetry` returns the writes each tick drained
since the last call. The F´ build's radio edge is an `FprimeStation` on the adapter, which takes its
`period_s` from it. The reasoning is in
[ADR 0004 rev 2](../docs/decisions/0004-hold-both-builds-to-one-fpp-contract-spoken-in-fprime-s-names.md).
