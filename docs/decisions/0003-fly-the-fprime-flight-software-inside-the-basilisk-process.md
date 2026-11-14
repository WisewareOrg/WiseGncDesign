# 0003 — Fly the F´ flight software inside the Basilisk process

**Status:** accepted
**Decided:** 2026-11-13 (issue 51 two edges design; issue 52 tooling checks)
**Rev:** 3

## Revisions

- **rev 3** — 2026-11-13 — rewritten to two edges: HardwareEdge, the partitions, the lab, the power
  cycle, one extension per configuration and rates as FPP constants, with the checks' results;
  corrects rev 2's "an `FW_ASSERT` aborts the process" (issue 52 tooling checks).
- **rev 2** — 2026-11-13 — stated timelessly and without naming an algorithm; the command and
  telemetry decisions are ADR 0004 rev 1 (issue 38 commands into the F´ build).
- **rev 1** — 2026-11-12 — first written (issue 31 F´ in Basilisk).

## Context

The algorithms are written in Python first and flown with no F´ build. F´ is good flight software
in its own right, not a mirror of the Python build. Both builds fly the same missions, scenarios and
cases, and are judged alike. Basilisk only runs and schedules the dynamics: no flight software
telemetry or command is a Basilisk message.

In the build of main at `6f6276e`, one object per build does bus I/O, unit conversion, commands,
telemetry and the algorithm. The F´ build's sim glue, `SimBridge`, is wired by hand for one
algorithm, and the Python build reads Basilisk by field name. A second algorithm has no place to sit,
and the glue grows with every algorithm.

Each build meets the world at two edges. RadioEdge, the ground, is ADR 0004 rev 2. HardwareEdge,
the sim, is this ADR. Three constraints hold throughout: components are semi-realistic all the way
through; the sim stays fast, about 0.28 s per case for the F´ build (Leo500, lo fidelity); and flying
the F´ build with F´'s real ground data system stays possible.

## Decision

### Two repositories, glue only at the edges

- **WiseDynamics owns the sim side** and knows nothing of FPP, F´ or missions: the run loop, devices
  by role (IMU readers, actuator writers, starting with a reaction wheel), run files, sessions, and a
  generic FSW host module. A build plugged into the host provides `period_s`, `boot()` and
  `tick(t, messages_by_role) -> actuator_commands_by_role`, and the host keeps a build's exceptions
  whole.
- **WiseGncDesign owns only what it needs to operate the flight software and judge its results.**
- **HardwareEdge is Basilisk message objects in by role, and actuator commands out by role.**
  WiseDynamics converts nothing. The by-role mappings stay mappings: roles vary per vehicle.

### Partitions, one frame per tick

Each tick is one frame: RIO in, CDH in, GNC, CDH out, RIO out.

| Partition | Job | Python build `fsw/python/` | F´ build `fsw/fprime/` |
|---|---|---|---|
| RIO | bus I/O | `rio/`: Basilisk messages in, actuator commands out | `rio/`: SimHub |
| CDH | units, commands, telemetry, parameters | `cdh/`: generated converters, dispatch by name, raw telemetry log, parameter reader | `cdh/`: GroundLink, stock CommandDispatcher, PrmDb, generated CDH components |
| GNC | the algorithms | `gnc/`: runs `fsw/fpp/gnc/` | `fsw/fpp/gnc/` plus each algorithm's C++ |
| Platform | clock, tick, tasks | `platform/`: frame scheduling | `platform/`: SimTime, rate-group driver, Cooperative/SimTask |

- **GNC touches neither edge, and each build has its own CDH**, however thin.
- **The Python frame runner is only those four folders.** Events, sequencing, health and data typing
  are not its job.
- **An algorithm sits in `algorithms/<name>/`**: its notebook, its `<Name>.fpp` and an optional C++
  component. `fsw/fprime/configurations/` holds one deployment per configuration, importing the
  partitions.
- **No file under `fsw/fprime/`, `fsw/python/` or `lab/` names an algorithm.**

### Inside or outside `_wise_fsw`

- **If a real F´ deployment would have it, it is inside `_wise_fsw`.** Each stand-in replaces one
  real thing: SimHub the bus driver, GroundLink the whole comm stack, SimTime the time source.
- **The pins are compiled into `_wise_fsw` as a test connector.** They are the lab's, not the
  deployment's.
- **Everything else is ground segment (ADR 0004 rev 2) or lab.**

### The deployment

- **F´ runs in Basilisk's process, ticked on simulated time.** Nothing in it runs on a thread of its
  own: its tasks run on the tick (Cooperative/SimTask), so a tick finishes before the call returns
  and a case reproduces from its seed.
- **The binding is a small hand-written pybind11 module**, with no fprime-python dependency.
- **One extension per configuration**, `_wise_fsw_<configuration>`, chosen by `Mission(gnc=…)`.
- **Rates are FPP constants in the GNC sub-topology**, e.g. `constant navDivider = 1`. The
  sub-topology owns its rate-group instances and member order. F´'s configuration code passes the
  generated constants (`FppConstantsAc.hpp`) to `configure()`, and the Python frame runner reads the
  same constants (ADR 0004 rev 2). Platform keeps only the base tick.

### The F´ build at HardwareEdge: the lab

The F´ build meets HardwareEdge as a hardware-in-the-loop rig would. The lab holds no per-algorithm
code.

- **Bus structs** in `fsw/fpp/interfaces/` mirror Basilisk messages by hand, each held to the real
  message's fields by a test (issue 56 FPP types: the IMU bus struct held to Basilisk).
- **The bus emulator** turns Basilisk messages into bus-struct bytes and back. It is generated from
  the bus structs.
- **SimHub** takes those bytes on F´ `serial` ports and delivers them to typed ports, as F´'s
  `GenericHub` does. The bytes are F´'s own serialization of the struct.
- **The generated CDH component** converts bus types to the GNC's FPP types and back. The generator
  is ADR 0004 rev 2's.
- **The pins** boot, tick, push and drain bytes by port, take command packets in and give telemetry
  writes out. Nothing runs at import: `boot(prm_path)` sets up the topology, and PrmDb reads the
  case's parameter file there (ADR 0004 rev 2). A second `boot` in one copy raises.
- **The power cycle is a fresh copy of the extension per case.** One entry point, the lab's
  power-cycle function, copies and loads it, and nothing else imports `_wise_fsw`:
  - the `.so` is copied into a per-process temp dir under a counter-numbered name, and each copy is
    kept until the process exits;
  - it loads under the spec name `_power_cycle_<n>.<extension>`, with `n` from a process counter,
    never the case index, and never enters `sys.modules`;
  - the rebuilt-on-disk check stats the source `.so`, and a rebuilt extension is refused until the
    kernel restarts.
- **An F´ assert raises in Python; a copy that raised is never reused.** A throwing `Fw::AssertHook`
  in the pins, registered before setup, keeps the assert's text.
- **The Python build builds fresh objects per case.**

### Recording a flight

- **A flight's end belongs to the scenario.** The one stopping rule the harness binds is the TST
  definition's duration.
- **Each flight's `flight.json` records which FSW flew.** `build` is the host's build identity: for
  the F´ build, `frameworkVersion` (the F´ tag) and `projectVersion` from the dictionary's metadata.
  `just fsw` forces F´'s version stamp on every build, so `projectVersion` names the commit, with
  `-dirty` for an uncommitted tree. Each case merges `build` in atomically, without a lock.

### Dependencies

- **F´ and Eigen are fetched by tag, with no git submodule.** F´'s tag is `fprime_tag` in the
  `justfile`, Eigen's is a FetchContent git tag, and Renovate's regex managers bump both. F´'s tag,
  `fprime-tools` and `fprime-fpp` arrive as one update, and `pins_test.py` holds those tools, `cmake`
  and `ninja` to the versions F´'s clone pins.

## Results

The checks ran on F´ v4.4.2, Python 3.14.7 and pybind11 3.1.0, on branch `spike/two_edges`.

### Power cycle: PASS (commit `f618d9e`, `spikes/power/`)

`spikes/power/run_all.sh` flies Leo500 cases through the repo's `Ground`, then `compare.py` and
`summarize.py` read the results.

- **State does not leak.** Case 3 flown alone, after case 7, and first and third in 3, 7, 3, against
  the shared extension: the command logs and all 15 datasets (85149 rows) are bytewise equal. Case 7
  differs from case 3, so the comparison can fail.
- **Time per case, n = 100:** fresh copy 0.282 s mean, shared extension 0.288 s.
- **RSS per worker, `gc.collect()` after each case:** fresh copy 261 MB to 334 MB, about 0.73 MB
  per case; shared extension flat. Each copy maps its own `.so` and topology heap, which are never
  unloaded. The growth from issue 49 (cases flown with a ground stay in memory) did not appear in the
  shared runs, so it was neither counted nor excluded here.

**Correction the check forced.** A copy loaded under the spec name `_wise_fsw` returns the first
copy's module: pybind11 caches a finished module by its spec name. A unique dotted name per copy,
whose last part is the module name, gives each copy its own module. Two copies booted in one
process, with only one stepped, drain 1 and 0 telemetry writes.

### SimHub on F´ serial ports: PASS (commit `9eccec3`, `spikes/fprime/`)

`python spike_check.py a` pushes an IMU bus struct written by Python onto `simHub.busIn` and echoes
it back through a typed port:

```
IMU_SERIALIZED_SIZE 56 struct.calcsize 56
python struct.pack: 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
F´ serializeTo    : 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
push status 0 -> imuSink got 1 123456789000 [0.01, -0.02, 0.03] [1.5, -2.25, 9.80665]
little-endian push decodes as 583948143490498560 [7.688e+284, …]
CHECK A PASS
```

F´'s serialization is big-endian, unpadded and unframed, members in declaration order, so
`struct.Struct(">Q3d3d")` writes it; the spike's struct leads with a `U64` time tag, which Basilisk's
IMU message lacks, so the check spans mixed widths. The little-endian push shows the comparison can
fail.

**Finding behind the assert hook.** Port calls are direct outside unit-test builds, so a
wrong-length push `FW_ASSERT`s, and in a Release build F´'s default handler prints and returns: a
55-byte push printed the assert and still delivered a partly filled struct. So the earlier claim
that an `FW_ASSERT` aborts the process was wrong, and the throwing hook replaces it.

### boot(prm_path): PASS (commit `9eccec3`)

`boot(prm_path)` registers the cooperative task registry, runs `setupTopology` with the path, and
raises on a second call. PrmDb takes the path in its `configComponents` phase and reads the file in
`readParameters`. A second process booted with another case's file read that case's `mu`,
4.9048695e12 against 3.986004418e14, so a path that never reached PrmDb would have shown.

## Alternatives considered

- **A reset handler per stateful component, in place of the power cycle.** Named as the fallback,
  not taken: the power cycle passed with no state leak and no time cost, and needs no reset code in
  any component.
- **One process per case.** Pays process start-up and import on every case.
- **Recycling a worker every K cases.** Not built: campaigns run on pytest-xdist workers that end
  with the session, about 85 MB per worker for a 920-case campaign on 8 workers, and xdist has no
  restart-after-N. Issue 59 power-cycle the F´ build per case reports peak RSS per worker on the full
  campaign; recycling is designed only if a measured campaign needs it.
- **A copy's spec name from the case index.** A kernel can fly the same case twice, and the repeated
  name returns the cached, already-flown copy. Rejected for a process counter.
- **Typed ports in place of SimHub.** Named as the fallback, not taken: SimHub passed, and a real
  bus driver takes bytes.
- **A length check in the pins or the bus emulator.** The pins would need per-port size knowledge,
  which is per-port glue at the edge, and the emulator is generated from the same struct. Rejected
  for the assert hook.
- **`FW_ASSERTIONS_ALWAYS_ABORT`.** It kills the worker and loses the case's failure. Rejected.
- **Rates in F´'s C++ configuration only, or rate groups in platform.** The Python build cannot
  read C++, so the two builds would carry two copies of each rate. Rejected for FPP constants.
- **A separate FSW process bridged over a socket.** No lockstep with simulated time without a tick
  protocol of its own. Rejected.
- **F´'s own timer, with components on OS threads.** It wakes on wall-clock time, so a case does not
  reproduce from its seed. Rejected.
- **FSW telemetry in Basilisk message structs.** It limits the FSW to fields Basilisk defines.
  Rejected.
- **fprime-python's autocoder in place of the hand-written binding.** Measured from clean checkouts:
  443 s to build against 32 s, 0.85 s per case against 0.76 s, no less glue, a clock that cannot be
  set from Python, unbound telemetry buffers, and a segfault at exit unless torn down first.
  Rejected.
- **F´ in a repository of its own.** Each algorithm and its F´ build are written side by side.
  Rejected.
- **The build identity in run-file attributes, or the commit alone.** The first needs the simulator
  changed; the second cannot tell two builds of one commit apart. Rejected.
- **F´ as a git submodule, Eigen as a hash-pinned tarball.** Renovate tracks neither by release tag.
  Rejected.

## Consequences

- A second algorithm joins a configuration in FPP, with no glue written for it in either build.
- The power cycle costs no measured time and about 0.73 MB of RSS per case per worker, never
  returned while the worker lives, plus 0.7 MB of disk per case until it exits (RAM where the temp
  dir is tmpfs). Reopened if a measured campaign's peak RSS per worker threatens the host: the
  choice is then recycling or reset handlers.
- An F´ assert fails the case in Python with F´'s own text. Until issue 59 power-cycle the F´ build
  per case adds the hook, an F´ assert in the Release build prints and the flight continues.
- Copies share no state, so more than one F´ build can be booted in one process.
- A rebuilt extension still needs a kernel restart.
- The deployment has F´'s real rate groups, CommandDispatcher and PrmDb, and differs from a standard
  deployment only in its threadless tasks, its three stand-ins and the pins.
- A stale extension shows as a `projectVersion` that differs from the run file's
  `versions_caller_commit`.
- The bus structs are a hand-kept mirror of Basilisk's messages; issue 56's test fails when one
  drifts.
- WiseDynamics' host module and actuator writers land first, since they make the homes this repo
  plugs into.
