# 0003 — Fly the F´ flight software inside the Basilisk process

**Status:** accepted
**Decided:** 2026-11-13 (issue 31: the two spikes and their discovery; issue 37: the dictionary; issue 38: commands)
**Rev:** 2

## Revisions

- **rev 2** — 2026-11-13 — the dictionary: a role's entries in shared FPP groups, array channels,
  and a Python build's dictionary generated from FPP alone (issue 37 the Python-first dictionary);
  commands through F´'s own dispatcher on a task with no thread, and `GroundLink` logging every
  telemetry write (issue 38 commands into the F´ build).
- **rev 1** — 2026-11-12 — first written (issue 31 F´ in Basilisk).

## Context

F´ is to be the flight software, and the Python C&DH stands in for it. Each algorithm and its F´
build are to be written side by side in this repository, and flown through the same missions,
scenarios, cases and judging as the notebook, so the two builds compare case by case. Basilisk only
arbitrates, schedules and runs the dynamics: no FSW telemetry or command is a Basilisk message. The
ground link that follows needs the F´ boundary to exist first.

Two spikes flew an F´ v4.4.2 build of one algorithm inside Basilisk. The first wraps the
deployment in a hand-written pybind11 binding. The second replaced that binding with fprime-python's
autocoder.

## Decision

### The deployment

- **F´ runs in Basilisk's process, as a passive deployment ticked on simulated time.** The
  deployment is a Python extension, `_wise_fsw`. A Basilisk module, `gnc_cdh.fprime.FprimeModule`,
  ticks it at the FSW rate, and the clock crosses into F´ as the simulation's integer nanoseconds.
  `SimTime` sets the clock, `SimBridge` sends the readings and drives the schedule, and
  `GroundLink` is the ground's side. Every component but the command dispatcher is passive, and the
  dispatcher runs on the tick's thread, so a tick finishes before the call returns, and a case
  reproduces from its seed. Sensor readings are the only Basilisk messages the deployment reads, and
  its telemetry never passes through a Basilisk message.
- **Commands go through F´'s own `Svc.CmdDispatcher`, unmodified, on an `Os::Task` with no
  thread.** `Os_Task_Sim`, which `fprime_target_implementations` chooses for `_wise_fsw`, starts no
  thread and reports itself cooperative, so F´ gives it the one-step routine that returns on an
  empty queue. `Sim::Cooperative` registers every task and queue, and the tick pumps the tasks round
  by round until no queue holds a message. A command uplinked before a step runs at that step,
  before the sensor readings and the schedule. A queue still holding messages after the pump's
  bound, 1000 rounds, raises an error naming it, so a component that keeps requeueing crashes the
  case instead of hanging it.
- **`GroundLink` carries the link in F´'s form.** Command packets go up to the dispatcher under a
  context the ground picks, and each response comes back as that context and its
  `Fw.CmdResponse`. Every telemetry write is logged with its F´ time tag, in the order written,
  and draining the log returns the writes since the last drain; nothing keeps a latest value. The
  binding's `uplink`, `telemetry` and `responses` are the link's calls. `boot` runs the commands
  left queued, clears the link, then sends each component its configuration, which leaves it idle,
  so a case keeps nothing of the one before it.
- **A write is tagged with the FSW time at the moment it is made.** A component therefore writes a
  value only at a time it holds for; a command that sets a state as of an earlier time writes no
  estimate until a step propagates it.
- **The binding is a small hand-written pybind11 module, with no fprime-python dependency.**
  fprime-python is reconsidered only once it fixes time, telemetry and build cost.
- **Each F´ component sits beside the algorithm it ports.** The repository root is F´'s project root
  (`cdh/fprime/settings.ini`). An algorithm's component `.fpp`, `.hpp` and `.cpp` sit in its
  package beside the notebook, the package ADR 0002 rev 1 lays out around each algorithm.
  `cdh/fprime/` holds the rest of the F´ project: the interface types, the sim-side components, the
  topology and the binding.
- **An algorithm takes its configuration on an F´ port**, which `SimBridge` sends at boot, so
  nothing reaches past the F´ model. What the ground sets during a flight arrives by command.

### The dictionary

- **The FPP model is the dictionary's source, and F´'s generated JSON dictionary is its published
  form.** Python reads the JSON through one module, `gnc_cdh.dictionary`, which encodes and decodes
  commands and channels in F´'s bytes. It codes primitives, enums, and arrays of primitives or of
  such arrays; a channel of any other type fails the dictionary's load, naming the channel. A value
  a Python algorithm writes is packed into its channel's type, so one that F´ would not pack, such
  as `None`, a string or a wrong shape, fails naming the channel.
- **A role's shared entries are `.fppi` groups under `cdh/fprime/Interfaces/<Role>/`, which a
  component includes.** Each entry is defined in one place, so two algorithms filling a role cannot
  drift apart on it.
- **A vector is one array channel**, such as a `Gnc.Vector3` or a `Gnc.Quaternion`, written in
  one write, so no reader rebuilds a vector by name and a quaternion cannot be split across ticks.
- **A role is an instance name.** Entries are named `<instance>.<entry>`, the deployment prefix
  dropped, so a contract reads `<role>.<entry>` whichever build flew. A command has one owning
  instance.
- **A Python build's dictionary is generated from FPP alone.** The algorithm's component `.fpp`
  sits beside its notebook from the start, declaring its entries with no C++.
  `Dictionary.from_component` instances that component alone in a deployment it writes only into
  the temporary directory `fpp-to-dict` runs in. It needs the F´ source clone and no compiler or F´
  build, and writes nothing into the tree. It is generated once per process for each content of
  its inputs. The Python build never reads WiseFsw's dictionary, so it does not depend on the F´
  build.
- **A drift check holds the two builds to one contract.** A ported algorithm's F´ test asserts that
  its Python build's entries equal WiseFsw's for its instance, IDs and opcodes aside. It also fails
  when the model changed and the F´ build was not rebuilt.
- **The F´ host's one algorithm-specific piece is named**: `_ESTIMATE` in `gnc_cdh.fprime`, the
  channel each estimate the host records is read from.

### Recording a flight

- **Each host implements one recording method, `fly(run) -> datasets`.** The harness binds the
  scenario and its stopping rule into `run`. The host calls `run` with itself and the datasets it
  records, and adds whatever it records after the run. A host never sees the scenario or a
  duration, and the harness imports no host by type.
- **A flight's end belongs to the scenario**, and later to a ground procedure, never to a fixed
  length. The simulator stops only on time, so the one stopping rule the harness binds is the TST
  definition's duration.
- **Each flight's `flight.json` records which FSW flew**, beside the facts ADR 0002 rev 1 records
  there for the judge. `fsw` is the FSW builder's name, and `build` is the host's build identity:
  - for the F´ host, the host, `frameworkVersion` (the F´ tag) and `projectVersion`, read from the
    dictionary's metadata;
  - for the Python host, the host.

  The base facts are written before a case flies. `build` is merged in once a case has built its
  host. `just fsw` forces F´'s version stamp on every build, so `projectVersion` names the commit
  the extension was built from, with a `-dirty` suffix when built from an uncommitted tree.

### Dependencies

- **F´ and Eigen are fetched by tag, with no git submodule.**
  - F´'s release tag is one line, `fprime_tag` in the `justfile`. `just _sync` shallow-clones that
    tag into the gitignored `cdh/fprime/lib/fprime`. It clones again when the clone's tag cannot be
    read as the pinned one.
  - CMake's FetchContent fetches Eigen by git tag.
  - Renovate's regex managers bump both tags. F´'s tag, `fprime-tools` and `fprime-fpp` arrive as
    one update, which CI proves together.
  - Renovate leaves `cmake` and `ninja` alone, and `cdh/fprime/pins_test.py` holds them, with the
    other two tools, to the versions F´'s clone pins.

### Not decided here

- The ground: a ground station as its own process, and each host flying on the link.
- **One F´ topology per process holds one instance per role.** Because a role is an instance
  name, a second F´ implementation of a role has to replace the first in the topology, which
  breaks the first one's parity and drift checks. The sim side is written for the sensors and
  configuration of the algorithm it hosts: `SimBridge`'s ports, the binding's `boot` and `step`,
  and `FprimeModule`'s constructor. Porting an algorithm adds its component, its ports, its CMake,
  the topology instance and a builder, and no more only when it reuses those sensors and that
  configuration. An algorithm with different sensors or configuration also changes `Sim.fpp`,
  `SimBridge`, the binding and `FprimeModule`. The options:
  - one F´ deployment per ported algorithm, mirroring the Python build's generated deployment;
    unproven, since whether two F´ extensions can load in one process is not known;
  - distinct instance names per algorithm in one `WiseFsw`, which breaks a role being an instance
    name;
  - a rebuild per switch, which needs nothing new.

  The tripwire is the second F´ port, and nothing is built for it before then.

## Alternatives considered

- **A separate FSW process, bridged to Basilisk over a socket.** It has no lockstep with simulated
  time unless it gets a tick protocol of its own. Rejected for the in-process deployment.
- **F´'s own timer, with active components on OS threads.** It wakes on wall-clock time, so a case
  does not reproduce from its seed. Rejected for a passive deployment ticked on simulated time.
- **A passive stand-in for the command dispatcher.** About 80 lines of C++ reimplementing
  registration, the malformed-packet and invalid-opcode responses and tracking, which drift from
  F´'s. Rejected for the stock dispatcher on a task with no thread.
- **The stock dispatcher never started, its queue drained by the tick.** Not feasible:
  `CommandDispatcherImpl` is `final` and its dispatch is protected, so nothing outside it can drain
  an unstarted queue.
- **`TlmCapture` kept, holding each channel's latest value, with the uplink added to `SimBridge`.**
  A latest-value table lets whoever reads it choose the telemetry rate, and drops every write
  between reads. Rejected for one component on the ground's side that logs every write.
- **Clearing the dispatcher's command tracking at boot, by `CMD_CLEAR_TRACKING`.** Every command
  handler is sync and the pump runs every queue empty, so tracking holds nothing across a boot, and
  no test can fail without the clear. Rejected until a command handler is async, which is the
  tripwire for it.
- **FSW telemetry in Basilisk message structs.** It limits the FSW to fields Basilisk happens to
  define, and puts Basilisk inside the FSW's interface. Rejected: telemetry stays on the F´ side.
- **fprime-python's autocoder in place of the hand-written binding.** The second spike measured it
  against the first, from clean checkouts:
  - a clean build took 443 s and 285 compiles, against 32 s and 166;
  - a Monte Carlo case took 0.85 s, against 0.76 s;
  - it saved no code: 647 lines of hand-written glue, against 665;
  - a Python handler gets a copy of `Fw::Time` and no setter is bound, so a Python clock cannot
    serve time, and the algorithm never propagated;
  - `Fw::TlmBuffer` and the port-count methods are unbound;
  - the process segfaults at exit unless the deployment is torn down first;
  - only Python components can be reached from Python, which forces the design;
  - the project has one maintainer plus a bot, no releases, and exact pins on its own dependencies.

  Rejected: its time and telemetry bindings do not work for this use, and it costs more to build
  and to fly.
- **F´ in a repository of its own.** Rejected: each algorithm and its F´ build are written side by
  side and compared.
- **A generic F´ host, with the channel-to-estimate mapping moved beside the algorithm.** Rejected:
  generality with one consumer. The mapping stays one named piece of the host.
- **Each vector component as a scalar channel.** Every reader rebuilds the vector by name and
  checks that its parts were written together, and a quaternion over four channels is not one
  write. Rejected for array channels.
- **A Python build flying against WiseFsw's dictionary.** It makes the Python build depend on the F´
  build. Rejected.
- **An algorithm declaring its entries in Python, with FPP generated at port time.** The contract's
  source switches at port time, a Python-to-FPP generator must map types, units and enums, and drift
  is found at port time instead of being impossible. Rejected for FPP from the start.
- **The generated deployment written beside the algorithm.** It is a file in the tree that parallel
  test workers race to write. Rejected for the temporary directory.
- **Resolving the framework files each call with `fpp-locate-defs` and `fpp-depend`.** It costs
  1.2 s once and 0.28 s per call. Rejected for a fixed list of framework files, which fails loudly,
  naming the undefined symbol, when a model reaches outside it.
- **An algorithm's configuration set by public C++ methods the binding calls directly.**
  The call is outside any port, so the binding reaches past the F´ model. Rejected for ports.
- **Each host logging its own estimate.** It moves the Python build's recording off Basilisk's
  recorders, which no need asks for. Rejected.
- **A duration parameter on the recording method.** Rejected: a flight is not defined by a fixed
  simulated length.
- **`fly(scenario, stop)`** and **a stop value type.** Rejected for `fly(run)`: the harness binds
  the scenario and its stopping rule into one callable, and the host never sees the scenario or its
  stopping rule.
- **The build identity in run-file attributes.** Rejected: it would need the simulator changed.
- **The repository commit alone as the build identity.** Rejected: it cannot tell two builds of one
  commit apart.
- **F´ as a git submodule.** Rejected: Renovate's submodule manager is off in the preset this
  repository extends, and it tracks commits, not release tags.
- **Eigen as a tarball pinned by hash.** Rejected: Renovate cannot recompute the hash when it bumps
  the version.

## Consequences

- The two builds fly the same missions, scenarios and cases and are judged alike, so they compare
  case by case. Parity tests hold them to rounding.
- A further host implements `fly` and `build`, and the harness needs no change for it.
- Two builds of one algorithm are told apart in the judge's session even at one repository commit.
  A stale extension shows as a `projectVersion` that differs from the run file's
  `versions_caller_commit`.
- Each case merges `build` into `flight.json` atomically, without a lock. `build` can therefore
  rarely be missing from a flight that already has a crashed case, when that case's base write
  overlapped another case's merge; any later successful case restores it.
- The deployment is one per process, so one F´ host flies at a time in a process.
- The deployment departs from a standard F´ deployment on purpose: no timer or rate groups,
  `GroundLink` logging every write in place of F´'s downlink, no events or parameters, and one
  active component, the dispatcher, run on the tick's thread.
- A clean `just fsw` also compiles the dispatcher and `Os_Task_Sim`; nothing else in the build
  changes for commands.
- An `FW_ASSERT` in F´ code aborts the process, so it ends a test worker rather than failing a
  case. A cooperative task asked to sleep asserts; nothing in the deployment sleeps.
- An algorithm flies in Python before an F´ build of it exists, and the Python path needs no
  compiler or F´ build, only the F´ clone. A new channel or command is two edits while
  prototyping: the `.fpp` line and the Python that writes or handles it.
- Generating a Python build's dictionary takes 0.1–0.3 s once per process for each content of its
  model.
- An F´ release bump arrives as one Renovate update with the tools F´ pins, and a tool pin that
  drifts from F´'s fails `cdh/fprime/pins_test.py`.
