# 0003 — Fly the F´ flight software inside the Basilisk process

**Status:** accepted
**Decided:** 2026-11-13 (issue 51 two edges design; issue 52 tooling checks)
**Rev:** 3

## Revisions

- **rev 3** — 2026-11-13 — rewritten to two edges: HardwareEdge, the partitions, the lab, the power
  cycle, one extension per configuration and rates as FPP constants, with the checks that support
  them; corrects rev 2's "an `FW_ASSERT` aborts the process" (issue 52 tooling checks).
- **rev 2** — 2026-11-13 — stated timelessly and without naming an algorithm; the command and
  telemetry decisions are ADR 0004 rev 1 (issue 38 commands into the F´ build).
- **rev 1** — 2026-11-12 — first written (issue 31 F´ in Basilisk).

## Context

The algorithms are written in Python first and flown with no F´ build. F´ is good flight software
in its own right, not a mirror of the Python build. Both builds fly the same missions, scenarios and
cases, and are judged alike. Basilisk only runs and schedules the dynamics: no flight software
telemetry or command is a Basilisk message.

In the baseline build, one object per build does bus I/O, unit conversion, commands, telemetry and
the algorithm. The F´ build's sim glue, `SimBridge`, is wired by hand for one algorithm, and the
Python build reads Basilisk by field name. A second algorithm has no place to sit, and the glue grows
with every algorithm.

Each build meets the world at two edges. RadioEdge, the ground, is ADR 0004 rev 2. HardwareEdge,
the sim, is this ADR. Three constraints hold throughout: components are semi-realistic all the way
through; the sim stays fast; and flying the F´ build with F´'s real ground data system stays
possible.

### The checks

They ran on branch `spike/two_edges` against the baseline: main `6f6276e`, F´ v4.4.2, fpp 3.4.0,
pybind11 3.1.0.

**Power cycle: PASS** (`f618d9e`, `spikes/power/`). A fresh copy of the extension per case leaks no
state and costs no time. `spikes/power/run_all.sh`, then `python summarize.py res/*100_gc.log`:

```
res/shared100_gc.log: n=100 time mean 0.288 median 0.286 | rss start 261 end 260 MB, slope -8 kB/case
res/fresh100_gc.log: n=100 time mean 0.282 median 0.281 | rss start 261 end 334 MB, slope 737 kB/case
```

`compare.py` found case 3's command log and 15 datasets bytewise equal flown alone, after case 7,
first and third in 3, 7, 3, and on the shared extension; case 7 differs from case 3, so a leak would
have shown as unequal datasets. A copy loaded under the spec name `_wise_fsw` returned the first
copy's module, because pybind11 caches a module by spec name; a unique dotted name per copy fixed
it. The driver did not reproduce the growth in issue 49 every case flown with a ground stays in
memory, so that growth was neither counted nor excluded. Not covered: the copies ran setup at import,
so a fresh copy, `boot(prm_path)` and PrmDb's load were never run together.

**SimHub on F´ serial ports: PASS** (`9eccec3`, `spikes/fprime/`). Bytes Python's `struct.pack`
writes for a bus struct equal F´'s serialization, and SimHub delivers them as the typed struct.
`python spike_check.py a`:

```
python struct.pack: 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
F´ serializeTo    : 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
push status 0 -> imuSink got 1 123456789000 [0.01, -0.02, 0.03] [1.5, -2.25, 9.80665]
little-endian push decodes as 583948143490498560 [7.688e+284, …]
```

The little-endian push is the failure the comparison would have shown. The format is big-endian,
unpadded and unframed, in declaration order (`struct.Struct(">Q3d3d")`). A 55-byte push asserted,
printed, and delivered a partly filled struct. Not covered: an assert thrown through F´ into
pybind11.

**boot(prm_path): PASS** (`9eccec3`). Setup moves out of import into `boot(prm_path)`, and PrmDb
reads the case's file there. `python spike_check.py b <case>.dat` from two processes with two files:
each read its own case's `mu`, so a path that never reached PrmDb would have shown as equal values.

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
- **No file in the generic code names an algorithm:** `fsw/fprime/cdh/`, `fsw/fprime/rio/`,
  `fsw/fprime/platform/`, `fsw/python/` and `lab/`.
- **A configuration in `fsw/fprime/configurations/` is named for the configuration**, and reaches
  algorithms only through its GNC sub-topology in `fsw/fpp/gnc/`, so no file under
  `configurations/` names an `algorithms/` path.

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
  `_wise_fsw` names whichever configuration's extension is flying.
- **Rates are FPP constants in the GNC sub-topology**, e.g. `constant navDivider = 1`. The
  sub-topology owns its rate-group instances and member order. F´'s configuration code passes the
  generated constants (`FppConstantsAc.hpp`) to `configure()`, and the Python frame runner reads the
  same constants (ADR 0004 rev 2). Platform keeps only the base tick.

### The F´ build at HardwareEdge: the lab

The F´ build meets HardwareEdge as a hardware-in-the-loop rig would. The lab holds no per-algorithm
code.

- **Bus structs** in `fsw/fpp/interfaces/` mirror Basilisk messages by hand, each held to the real
  message's fields by a test.
- **The bus emulator** turns Basilisk messages into bus-struct bytes and back. It is generated from
  the bus structs.
- **SimHub** takes those bytes on F´ `serial` ports and delivers them to typed ports, as F´'s
  `GenericHub` does. The bytes are F´'s own serialization of the struct.
- **The generated CDH component** converts bus types to the GNC's FPP types and back. The generator
  is ADR 0004 rev 2's.
- **The pins** boot, tick, push and drain bytes by port, take command packets in and give telemetry
  writes out. Nothing runs at import: `boot(prm_path, prm_ids)` sets up the topology, PrmDb reads
  the case's parameter file there, and boot raises unless every parameter is valid (ADR 0004 rev 2).
  A second `boot` in one copy raises.
- **The power cycle is a fresh copy of the extension per case.** One entry point, the lab's
  power-cycle function, copies and loads it, and nothing else imports `_wise_fsw`:
  - the `.so` is copied into a per-process temp dir under a counter-numbered name, and each copy is
    kept until the process exits;
  - it loads under the spec name `_power_cycle_<n>.<extension>`, with `n` from a process counter,
    never the case index, and never enters `sys.modules`;
  - the rebuilt-on-disk check stats the source `.so`, and a rebuilt extension is refused until the
    kernel restarts: picking one up mid-kernel would change how a notebook session behaves on a
    rebuild, and could fly a new extension against a dictionary cached from the old one.
- **An F´ assert raises in Python; a copy that raised is never reused.** In a Release build F´'s
  default assert handler prints and returns. The pins register a throwing `Fw::AssertHook` before
  setup, which keeps the assert's text.
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

## Alternatives considered

- **A reset handler per stateful component, in place of the power cycle.** Named as the fallback,
  not taken: the power cycle passed with no state leak and no per-case cost, and needs no reset code
  in any component.
- **One process per case.** Pays process start-up and import on every case.
- **Recycling a worker every K cases.** Not built: campaigns run on pytest-xdist workers that end
  with the session, so a worker's growth is bounded by its share of one campaign, and xdist has no
  restart-after-N. Peak RSS per worker is reported on a full campaign; recycling is designed only if
  one needs it.
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
- **fprime-python's autocoder in place of the hand-written binding.** The second spike of
  issue 31 F´ in Basilisk measured it from clean checkouts:
  443 s to build against 32 s, 0.85 s per case against 0.76 s, no less glue, a clock that cannot be
  set from Python, unbound telemetry buffers, and a segfault at exit unless torn down first.
  Rejected.
- **F´ in a repository of its own.** Each algorithm and its F´ build are written side by side.
  Rejected.
- **An algorithm's configuration on an F´ port, sent at boot by the sim glue.** It is per-algorithm
  glue outside the FPP contract, and parity cannot see it. Rejected for F´ parameters, which are part
  of the contract both builds fly (ADR 0004 rev 2).
- **The build identity in run-file attributes, or the commit alone.** The first needs the simulator
  changed; the second cannot tell two builds of one commit apart. Rejected.
- **F´ as a git submodule.** Renovate's submodule manager is off in the preset this repository
  extends, and it tracks commits, not release tags. Rejected.
- **Eigen as a hash-pinned tarball.** Renovate cannot recompute the hash when it bumps the version.
  Rejected.

## Consequences

- A second algorithm joins a configuration in FPP, with no glue written for it in either build.
- The power cycle has no measurable per-case cost against the shared extension. RSS grows linearly
  per case per worker, one mapped copy each, never returned while the worker lives, and each copy's
  file stays on disk until the process exits (RAM where the temp dir is tmpfs). Reopened if a
  measured campaign's peak RSS per worker threatens the host: the choice is then recycling or reset
  handlers.
- The pins register a throwing hook, so that an F´ assert fails the case in Python with F´'s own
  text.
- Copies share no state, so more than one F´ build can be booted in one process.
- A rebuilt extension needs a kernel restart, though the power cycle would allow picking it up.
- The deployment has F´'s real rate groups, CommandDispatcher and PrmDb, and differs from a standard
  deployment only in its threadless tasks, its three stand-ins and the pins.
- A stale extension shows as a `projectVersion` that differs from the run file's
  `versions_caller_commit`.
- The bus structs are a hand-kept mirror of Basilisk's messages; a test fails when one drifts.
- WiseDynamics' host module and actuator writers land first, since they make the homes this repo
  plugs into.
