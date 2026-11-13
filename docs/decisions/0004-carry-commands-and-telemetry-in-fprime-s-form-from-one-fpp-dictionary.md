# 0004 — Carry commands and telemetry in F´'s form, from one FPP dictionary

**Status:** accepted
**Decided:** 2026-11-13 (issue 37 the dictionary; issue 38 commands into the F´ build)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-13 — first written (issue 37 the dictionary; issue 38 commands into the F´
  build).

## Context

An algorithm flies in Python before any F´ build of it exists, and one ground commands either
build and records its telemetry. The F´ build runs inside Basilisk with nothing on a thread of its own
(ADR 0003 rev 2).

- **Commands.** The ground commands both builds in F´'s packet format, and the F´ build should
  dispatch them as F´ does, with F´'s own responses, without a thread.
- **The dictionary.** Both builds must hold one contract, and a Python build must fly before any F´
  build of its algorithm exists, with no compiler.
- **Vectors.** A position, a velocity and an attitude are each one quantity, and a reader judges
  each as one.
- **Telemetry.** The flight software decides what it writes and when. Analysis judges what it
  reports, so no write may be lost or resampled.

## Decision

### Commands go through F´'s own dispatcher, run on the tick

The stock `Svc.CmdDispatcher`, unmodified, with standard command connections, runs on
`Os_Task_Sim`, an `Os::Task` with no thread that reports itself cooperative. F´ gives such a task
its one-step routine, which returns on an empty queue, and the tick runs it until every queue is
empty. A command uplinked before a step runs at that step.

### FPP is the dictionary's one source

The FPP model is the source, and F´'s generated JSON dictionary is its published form. A role's
shared entries are `.fppi` groups under `cdh/fprime/Interfaces/<Role>/` that a component includes,
and a role is an instance name, so an entry reads `<role>.<entry>` in every build. A Python build's
dictionary is generated from the algorithm's `.fpp` alone with `fpp-to-dict`, against the F´ source
clone, with no compiler, no F´ build and nothing written into the tree.

### A vector is one array channel

A vector or quaternion is one channel of an array type, written in one write.

### Telemetry is pushed

Every telemetry write is logged with the flight software's own time tag at the moment of the write,
in the order written, and the log is drained. Nothing keeps a latest value, and nothing on the sim
side samples or decimates telemetry.

## Alternatives considered

### Commands

- **A hand-written passive dispatcher.** About 80 lines of C++ that reimplement registration, the
  malformed-packet and invalid-opcode responses and command tracking, and drift from F´'s. Rejected
  for the stock component.
- **The stock dispatcher never started, its queue drained from outside.** Not possible:
  `CommandDispatcherImpl` is `final`, and its dispatch is protected, so nothing outside the class
  can drain an unstarted queue.

### The dictionary

- **Commands and telemetry declared in Python, with FPP generated at port time.** The contract's
  source switches at port time, a Python-to-FPP generator must map types, units and enums, and
  drift is found at port time instead of being impossible. Rejected for FPP from the start.
- **A Python build reading the F´ build's JSON dictionary.** It makes the Python build depend on the
  F´ build, so an algorithm needs a compiler and an F´ component before it can fly in Python.
  Rejected.
- **The generated deployment written into the tree beside the algorithm.** Every test worker
  rewrites it, and the write is not atomic, so parallel workers on a fresh checkout race and one
  can hand `fpp-to-dict` an empty deployment. It is also a build product in the source tree.
  Rejected for a temporary directory.
- **A role's entries as an FPP `interface`.** `fpp-check` rejects `telemetry` inside `interface`,
  which holds only ports. Rejected for included groups.

### Vectors

- **Each vector component as a scalar channel.** Every reader rebuilds the vector by name and
  checks that its parts were written together, and a quaternion over four channels is not one
  write. Rejected.

### Telemetry

- **The latest value of each channel, sampled on the simulation's recording grid.** The sim then
  sets the telemetry rate, decimates what the flight software writes, and loses every write between
  samples. Rejected: the flight software owns its rate.
- **A packed drain, one buffer per tick in place of one entry per write.** Measured at no wall-clock
  gain per case. Rejected for the simpler log.

## Consequences

### Commands

- A rejected packet gets F´'s own response, which is the response the Python build's decode gives
  the same bytes, so the two builds answer alike.
- The deployment holds one active component, run on the tick's thread; a clean build also compiles
  the dispatcher.
- Reopened if an F´ release drops the cooperative task routine, or a component needs to block or
  sleep, which a task with no thread cannot do.

### The dictionary

- A ported algorithm's F´ test asserts that its Python build's entries equal the F´ build's, IDs
  aside, so the two builds are held to one contract, and a stale F´ build fails it.
- A new channel or command is two edits while prototyping: the `.fpp` line and the Python that
  writes or handles it. The Python path needs the F´ source clone, and no compiler.
- Generating a Python build's dictionary takes 0.1–0.3 s, once per process for each content of its
  model.
- Reopened if generation becomes a visible share of a case, or `fpp-to-dict` stops shipping with
  the F´ tools.

### Vectors

- No reader rebuilds a vector, and no quaternion is split across ticks.
- Reopened if a consumer needs one component written apart from the others.

### Telemetry

- Every write reaches whoever drains the log. A channel never written is never reported.
- A write's tag is the flight software's clock when it is written, so a component writes a value
  only at a time the value holds for.
- Reopened if the per-write log shows in a per-case profile, or downlink is modelled. Downlink is
  then flight software components with flight software configuration on both builds, never a sim
  rate.
