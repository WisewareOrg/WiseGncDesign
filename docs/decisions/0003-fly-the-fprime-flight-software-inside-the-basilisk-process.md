# 0003 — Fly the F´ flight software inside the Basilisk process

**Status:** accepted
**Decided:** 2026-11-14 (issue 51 two edges design; issue 52 tooling checks)
**Rev:** 3

## Revisions

- **rev 3** — 2026-11-14 — each case flies a fresh copy of the extension, and an F´ assert raises
  in Python, with the checks that support them; corrects rev 2's "an `FW_ASSERT` aborts the
  process" (issue 52 tooling checks); the partitions are ADR 0005 rev 1; reverses rev 2's
  configuration on an F´ port for F´ parameters (ADR 0004 rev 2), which also takes the rejected FSW
  telemetry in Basilisk message structs and the boot(prm_path) check; the lab is ADR 0006 rev 1;
  fetching by tag and the flight's record become consequences, their rejected alternatives standing
  in rev 2, and a flight's end belonging to the scenario moves to the README (issue 85 one decision
  per ADR); the spike's bus driver is named by its job (issue 63 The lab's bus driver carries bus
  data into the F´ build).
- **rev 2** — 2026-11-13 — stated timelessly and without naming an algorithm; the command and
  telemetry decisions are ADR 0004 rev 1 (issue 38 commands into the F´ build).
- **rev 1** — 2026-11-12 — first written (issue 31 F´ in Basilisk).

## Context

F´ is good flight software in its own right, and its build flies the same missions, scenarios and
cases as the Python build, judged alike. Basilisk only runs and schedules the dynamics: no flight
software telemetry or command is a Basilisk message. The sim must stay fast, and flying the F´ build
with F´'s real ground data system must stay possible.

The sim this repository plugs into is WiseDynamics' FSW host. It gives a build Basilisk messages by
role and takes actuator commands back by role, through `period_s`, `boot()` and `tick()`.

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

**An assert in a Release build** (`9eccec3`). A 55-byte push through the spike's bus driver
asserted, printed, and delivered a partly filled struct: F´'s default assert handler prints and
returns. Not covered: an assert thrown through F´ into pybind11.

## Decision

- **F´ runs in Basilisk's process, ticked on simulated time.** Nothing in it runs on a thread of its
  own, so a tick finishes before the call returns and a case reproduces from its seed.
- **The binding is a small hand-written pybind11 module**, with no fprime-python dependency.
- **Each case flies a fresh copy of the extension**, the way a vehicle is power-cycled.
- **An F´ assert raises in Python; a copy that raised is never reused.**
- **The build meets the sim through the lab**, a hardware-in-the-loop rig (ADR 0006 rev 1).

## Alternatives considered

- **A separate FSW process bridged over a socket.** No lockstep with simulated time without a tick
  protocol of its own. Rejected.
- **F´'s own timer, with components on OS threads.** It wakes on wall-clock time, so a case does not
  reproduce from its seed. Rejected.
- **fprime-python's autocoder in place of the hand-written binding.** The second spike of issue 31
  F´ in Basilisk measured it from clean checkouts: 443 s to build against 32 s, 0.85 s per case
  against 0.76 s, no less glue, a clock that cannot be set from Python, unbound telemetry buffers,
  and a segfault at exit unless torn down first. Rejected.
- **A reset handler per stateful component, in place of a fresh copy.** Named as the fallback, not
  taken: the fresh copy passed with no state leak and no per-case cost, and needs no reset code in
  any component. Reopened if a measured campaign's peak RSS per worker threatens the host.
- **One process per case.** Pays process start-up and import on every case. Rejected.
- **`FW_ASSERTIONS_ALWAYS_ABORT`, in place of an assert that raises in Python.** It kills the worker
  and loses the case's failure, where a fault in an in-process F´ must fail the case. Rejected.
- **A length check in the pins or the bus emulator, in place of the raising assert.** It is per-port
  glue at the edge, and the emulator is generated from the same struct (ADR 0006 rev 1). Rejected.

## Consequences

- A fresh copy per case has no measurable per-case cost, and each copy's memory stays with its
  worker until the worker ends.
- Copies share no state, so more than one F´ build can be booted in one process.
- An F´ assert fails the case in Python with F´'s own text, instead of printing and flying on.
- The deployment has F´'s real rate groups, CommandDispatcher and PrmDb, and differs from a standard
  deployment only in its threadless tasks, its stub raw time, and the lab's stand-ins and pins.
- Each configuration's deployment is generated from its GNC sub-topology, and each configuration
  flies its own extension, `_wise_fsw_<configuration>`, chosen by `Mission(gnc=…)`.
- The rate groups' health telemetry is recorded on F´'s stub raw time, so it repeats from the seed
  with cycle times of 0; the trade is on issue 57 GNC sub-topology, and its cost is issue 80
  telemetry recording cost.
- F´ and Eigen are pinned by release tag, with no git submodule, and Renovate bumps both tags. F´'s
  arrives with `fprime-tools`, `fprime-fpp` and `fprime-gds` as one update, and a test holds those
  and `cmake` and `ninja` to F´'s pins.
- Each flight's `flight.json` records which FSW flew: `fsw` and `build` tell two builds of one
  commit apart, and the F´ build's `projectVersion` names the commit built from (`-dirty` when
  uncommitted), so a stale extension shows against the run file's `versions_caller_commit`.
- `build` is merged in per case without a lock, so it can rarely be missing from a flight with a
  crashed case; any later successful case restores it.
