# 0003 — Fly the F´ flight software inside the Basilisk process

**Status:** accepted
**Decided:** 2026-11-12 (issue 31: the two spikes and their discovery)
**Rev:** 2

## Revisions

- **rev 2** — 2026-11-13 — stated timelessly and without naming an algorithm; the command and
  telemetry decisions are ADR 0004 rev 1 (issue 38 commands into the F´ build).
- **rev 1** — 2026-11-12 — first written (issue 31 F´ in Basilisk).

## Context

F´ is to be the flight software, and the Python C&DH stands in for it. Each algorithm and its F´
build are to be written side by side in this repository, and flown through the same missions,
scenarios, cases and judging as the notebook, so the two builds compare case by case. Basilisk only
arbitrates, schedules and runs the dynamics: no FSW telemetry or command is a Basilisk message.

Two spikes flew an F´ v4.4.2 build of one algorithm inside Basilisk. The first wraps the deployment
in a hand-written pybind11 binding. The second replaced that binding with fprime-python's
autocoder.

## Decision

### The deployment

- **F´ runs in Basilisk's process, as a deployment ticked on simulated time.** The deployment is a
  Python extension, `_wise_fsw`. A Basilisk module, `gnc_cdh.fprime.FprimeModule`, ticks it at the
  FSW rate, and the clock crosses into F´ as the simulation's integer nanoseconds. `SimTime` sets
  the clock, and `SimBridge` sends the readings and drives the schedule. Nothing in the deployment
  runs on a thread of its own, so a tick finishes before the call returns, and a case reproduces
  from its seed. Sensor readings are the only Basilisk messages the deployment reads, and its
  telemetry never passes through a Basilisk message.
- **The binding is a small hand-written pybind11 module, with no fprime-python dependency.**
- **Each F´ component sits beside the algorithm it ports.** The repository root is F´'s project root
  (`cdh/fprime/settings.ini`). An algorithm's component `.fpp`, `.hpp` and `.cpp` sit in its
  package beside the notebook, the package ADR 0002 rev 1 lays out around each algorithm.
  `cdh/fprime/` holds the rest of the F´ project: the interface types, the sim-side components, the
  topology and the binding.
- **An algorithm takes its configuration on an F´ port**, which `SimBridge` sends at boot, so
  nothing reaches past the F´ model.

### Recording a flight

- **Each host implements one recording method, `fly(run) -> datasets`.** The harness binds the
  scenario and its stopping rule into `run`. The host calls `run` with itself and the datasets it
  records, and adds whatever it records after the run. A host never sees the scenario or a
  duration, and the harness imports no host by type.
- **A flight's end belongs to the scenario**, never to a fixed length. The simulator stops only on
  time, so the one stopping rule the harness binds is the TST definition's duration.
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

## Alternatives considered

- **A separate FSW process, bridged to Basilisk over a socket.** It has no lockstep with simulated
  time unless it gets a tick protocol of its own. Rejected for the in-process deployment.
- **F´'s own timer, with active components on OS threads.** It wakes on wall-clock time, so a case
  does not reproduce from its seed. Rejected for a deployment ticked on simulated time.
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
- **An algorithm's configuration set by public C++ methods the binding calls directly.** The call
  is outside any port, so the binding reaches past the F´ model. Rejected for ports.
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
- The deployment departs from a standard F´ deployment on purpose: no timer or rate groups, and no
  component on a thread of its own.
- An `FW_ASSERT` in F´ code aborts the process, so it ends a test worker rather than failing a
  case.
- An F´ release bump arrives as one Renovate update with the tools F´ pins, and a tool pin that
  drifts from F´'s fails `cdh/fprime/pins_test.py`.
