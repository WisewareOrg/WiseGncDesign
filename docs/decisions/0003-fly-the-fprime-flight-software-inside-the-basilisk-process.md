# 0003 — Fly the F´ flight software inside the Basilisk process

**Status:** accepted
**Decided:** 2026-11-14 (issue 51 two edges design; issue 52 tooling checks; issue 57 GNC
sub-topology)
**Rev:** 4

## Revisions

- **rev 4** — 2026-11-14 — the rate groups' health telemetry is not downlinked: health instances
  take base IDs from a reserved range the comm-stack stand-in drops (issue 57 GNC sub-topology).
- **rev 3** — 2026-11-13 — the F´ build meets the sim as a hardware-in-the-loop rig: the lab, a
  fresh copy per case, one extension per configuration and rates as FPP constants, with the checks
  that support them; the partitions are ADR 0005 rev 1; reverses rev 2's configuration on an F´
  port for F´ parameters (ADR 0004 rev 2); corrects rev 2's "an `FW_ASSERT` aborts the process"
  (issue 52 tooling checks).
- **rev 2** — 2026-11-13 — stated timelessly and without naming an algorithm; the command and
  telemetry decisions are ADR 0004 rev 1 (issue 38 commands into the F´ build).
- **rev 1** — 2026-11-12 — first written (issue 31 F´ in Basilisk).

## Context

F´ is good flight software in its own right, and its build flies the same missions, scenarios and
cases as the Python build, judged alike. Basilisk only runs and schedules the dynamics: no flight
software telemetry or command is a Basilisk message. The sim must stay fast, and flying the F´ build
with F´'s real ground data system must stay possible.

The sim this repository plugs into is WiseDynamics' FSW host. It gives a build Basilisk messages by
role and takes actuator commands back by role, through `period_s`, `boot()` and `tick()`. At
`6f6276e`, the F´ build's glue to the sim was wired by hand for one algorithm.

### The checks

They ran on branch `spike/two_edges` against main `6f6276e`, F´ v4.4.2, fpp 3.4.0,
pybind11 3.1.0.

**Power cycle: PASS** (`f618d9e`, `spikes/power/`). A fresh copy of the extension per case leaks no
state and costs no time. `spikes/power/run_all.sh`, then `python summarize.py res/*100_gc.log`:

```
res/shared100_gc.log: n=100 time mean 0.288 median 0.286 | rss start 261 end 260 MB, slope -8 kB/case
res/fresh100_gc.log: n=100 time mean 0.282 median 0.281 | rss start 261 end 334 MB, slope 737 kB/case
```

`compare.py` found case 3's command log and 15 datasets bytewise equal flown alone, after case 7,
flown first and third in the sequence 3, 7, 3, and on the shared extension; case 7 differs from case
3, so a leak would have shown as unequal datasets. A copy loaded under the same module name as an
earlier one returned the earlier copy's module, because pybind11 caches a module by name; a unique
name per copy fixed it. The driver did not reproduce the growth issue 49
reports (every case flown with a ground stays in memory), so that growth was neither counted nor
excluded. Not covered: the copies ran setup at import, so a fresh copy, `boot(prm_path)` and PrmDb's
load were never run together.

**SimHub on F´ serial ports: PASS** (`9eccec3`, `spikes/fprime/`). Bytes Python's `struct.pack`
writes for a bus struct equal F´'s serialization, and SimHub delivers them as the typed struct.
`python spike_check.py a`:

```
python struct.pack: 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
F´ serializeTo    : 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
push status 0 -> imuSink got 1 123456789000 [0.01, -0.02, 0.03] [1.5, -2.25, 9.80665]
little-endian push decodes as 583948143490498560 [7.688e+284, …]
```

The little-endian push is the failure the comparison would have shown. A 55-byte push asserted,
printed, and delivered a partly filled struct: in a Release build F´'s default assert handler prints
and returns. Not covered: an assert thrown through F´ into pybind11.

**boot(prm_path): PASS** (`9eccec3`). Setup moves out of import into `boot(prm_path)`, and PrmDb
reads the case's file there. `python spike_check.py b <case>.dat` from two processes with two files:
each read its own case's `mu`, so a path that never reached PrmDb would have shown as equal values.
The path enters per case: each case builds its own FSW object with the case's path, and that object
hands it to its copy's `boot`.

## Decision

### The deployment

The partitions inside each build are ADR 0005 rev 1.

- **F´ runs in Basilisk's process, ticked on simulated time.** Nothing in it runs on a thread of its
  own, so a tick finishes before the call returns and a case reproduces from its seed.
- **The binding is a small hand-written pybind11 module**, with no fprime-python dependency.
- **If a real F´ deployment would have it, it is inside `_wise_fsw`.** Each stand-in replaces one
  real thing: SimHub the bus driver, GroundLink the whole comm stack, SimTime the clock, its time
  source and its timer.
  Everything else is ground segment (ADR 0004 rev 3) or lab; the lab's pins are compiled in as a
  test connector.
- **One extension per configuration**, `_wise_fsw_<configuration>`, chosen by `Mission(gnc=…)`.
- **Rates are FPP constants in the GNC sub-topology**, which owns its rate groups; F´'s
  configuration code passes the generated constants to `configure()`.
- **The rate groups' health telemetry is not downlinked.** Health instances take base IDs from a
  reserved range that the comm-stack stand-in drops, so a new component is recorded with nothing
  registered for it.

### The lab: a hardware-in-the-loop rig

- **Bus structs** in FPP mirror Basilisk messages, each held to the real message by a test.
- **The bus emulator**, generated from the bus structs, turns Basilisk messages into their bytes.
- **SimHub** takes the bytes on F´ `serial` ports and delivers typed bus structs.
- **The generated CDH component** converts bus types to the GNC's FPP types and back.
- **The pins** move bytes, packets and telemetry, and set the topology up in `boot`, not at import.
- **Each case flies a fresh copy of the extension**, the way a vehicle is power-cycled.
- **An F´ assert raises in Python; a copy that raised is never reused.**

### Recording a flight

- **A flight's end belongs to the scenario**, never to a fixed length. The simulator stops only on
  time, so the one stopping rule the harness binds is the TST definition's duration.
- **Each flight's `flight.json` records which FSW flew**, beside the facts ADR 0002 rev 1 records
  there for the judge. `fsw` is the FSW builder's name, and `build` is the build's identity:
  - for the F´ build, its host's name, `frameworkVersion` (the F´ tag) and `projectVersion`, read
    from the dictionary's metadata;
  - for the Python build, its host's name.

  The base facts are written before a case flies. `build` is merged in once a case has built its
  host. `just fsw` forces F´'s version stamp on every build, so `projectVersion` names the commit
  the extension was built from, with a `-dirty` suffix when built from an uncommitted tree.

### Dependencies

- **F´ and Eigen are fetched by tag, with no git submodule.**
  - F´'s release tag is one line, `fprime_tag` in the `justfile`. `just _sync` shallow-clones that
    tag into the gitignored `fsw/fprime/lib/fprime`. It clones again when the clone's tag cannot be
    read as the pinned one.
  - CMake's FetchContent fetches Eigen by git tag.
  - Renovate's regex managers bump both tags. F´'s tag, `fprime-tools` and `fprime-fpp` arrive as
    one update, which CI proves together.
  - Renovate leaves `cmake` and `ninja` alone, and `fsw/fprime/pins_test.py` holds them, with the
    other two tools, to the versions F´'s clone pins.

## Alternatives considered

- **A reset handler per stateful component, in place of a fresh copy.** Named as the fallback, not
  taken: the fresh copy passed with no state leak and no per-case cost, and needs no reset code in
  any component. Reopened if a measured campaign's peak RSS per worker threatens the host.
- **One process per case.** Pays process start-up and import on every case. Rejected.
- **`FW_ASSERTIONS_ALWAYS_ABORT`, in place of an assert that raises in Python.** It kills the worker
  and loses the case's failure, where a fault in an in-process F´ must fail the case. Rejected.
- **A length check in the pins or the bus emulator, in place of the raising assert.** It is per-port
  glue at the edge, and the emulator is generated from the same struct. Rejected.
- **Typed ports in place of SimHub.** Named as the fallback, not taken: SimHub passed, and a real
  bus driver takes bytes.
- **Per-algorithm sim glue, as at `6f6276e`.** Every added algorithm or sensor needs C++ in the
  bridge and the pins. Rejected for the lab, which names no algorithm.
- **An algorithm's configuration on an F´ port, sent at boot by the sim glue.** It is per-algorithm
  glue outside the FPP contract, and parity cannot see it. Rejected for F´ parameters
  (ADR 0004 rev 3).
- **Rates in F´'s C++ configuration only.** The Python build cannot read C++, so the two builds
  would carry two copies of each rate. Rejected for FPP constants.
- **A list of the recorded instances, kept by hand or generated.** It needs a registration per
  component, or an autocoder. Rejected for the reserved range.
- **Recording the health telemetry with a simulated clock.** It records a row per channel per tick
  of constant data. Rejected.
- **Filtering the health telemetry on the ground or in the lab.** Every write still moves each
  tick, and the dictionary carries no component type to filter on. Rejected.
- **A separate FSW process bridged over a socket.** No lockstep with simulated time without a tick
  protocol of its own. Rejected.
- **F´'s own timer, with components on OS threads.** It wakes on wall-clock time, so a case does not
  reproduce from its seed. Rejected.
- **FSW telemetry in Basilisk message structs.** It limits the FSW to fields Basilisk defines.
  Rejected.
- **fprime-python's autocoder in place of the hand-written binding.** The second spike of issue 31
  F´ in Basilisk measured it from clean checkouts: 443 s to build against 32 s, 0.85 s per case
  against 0.76 s, no less glue, a clock that cannot be set from Python, unbound telemetry buffers,
  and a segfault at exit unless torn down first. Rejected.
- **F´ in a repository of its own.** Each algorithm and its F´ build are written side by side.
  Rejected.
- **The build identity in run-file attributes, or the commit alone.** The first needs the simulator
  changed; the second cannot tell two builds of one commit apart. Rejected.
- **F´ as a git submodule.** Renovate's submodule manager is off in the preset this repository
  extends, and it tracks commits, not release tags. Rejected.
- **Eigen as a hash-pinned tarball.** Renovate cannot recompute the hash when it bumps the version.
  Rejected.

## Consequences

- An added sensor is a bus struct and FPP wiring; no sim glue is written for it.
- A fresh copy per case has no measurable per-case cost, and each copy's memory stays with its
  worker until the worker ends.
- Copies share no state, so more than one F´ build can be booted in one process.
- An F´ assert fails the case in Python with F´'s own text, instead of printing and flying on.
- The deployment has F´'s real rate groups, CommandDispatcher and PrmDb, and differs from a standard
  deployment only in its threadless tasks, its three stand-ins and the pins.
- Adding a rate group is one more line, its base ID in the reserved range, and a test fails if one
  is outside it.
- A stale extension shows as a `projectVersion` that differs from the run file's
  `versions_caller_commit`.
- Each case merges `build` into `flight.json` atomically, without a lock, so `build` can rarely be
  missing from a flight that already has a crashed case; any later successful case restores it.
- An F´ release bump arrives as one Renovate update with the tools F´ pins, and a tool pin that
  drifts from F´'s fails `fsw/fprime/pins_test.py`.
- The bus structs are a hand-kept mirror of Basilisk's messages; a test fails when one drifts.
