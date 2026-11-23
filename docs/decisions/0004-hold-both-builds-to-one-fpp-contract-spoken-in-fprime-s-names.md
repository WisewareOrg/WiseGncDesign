# 0004 — Hold both builds to one FPP contract, spoken in F´'s names

**Status:** accepted
**Decided:** 2026-11-13 (issue 51 two edges design; issue 52 tooling checks)
**Rev:** 4

## Revisions

- **rev 4** — 2026-11-23 — telemetry crosses the edge packed: the F´ build's ground link packs each
  write into F´'s own `TlmPacket`, and the Python build logs a component's telemetry tuple once a
  frame; the raw tuple per write is rejected on its measured per-case cost, and the reopening
  condition it answered is removed (issue 122 Speed up flying a case with its ground).
- **rev 3** — 2026-11-22 — `parameters` also takes the case's vehicle, `parameters(scenario, vehicle)`,
  since WiseDynamics' scenario no longer builds the vehicle a notebook reads (issue 19 the org Python
  standard).
- **rev 2** — 2026-11-13 — retitled from "Carry commands and telemetry in F´'s form, from one FPP
  dictionary" and rewritten to two edges: RadioEdge in F´'s names, the F´ ground station, typing
  after the run, FPP as the contract read through the native `fpp to-json`, generated named tuples,
  parameter files, and parity as an analyzer; with the checks that support them (issue 52 tooling
  checks); rates as FPP constants (issue 57 GNC sub-topology); the rejected configuration on an F´
  port, the rejected FSW telemetry in Basilisk message structs and the boot(prm_path) check, moved
  from ADR 0003 rev 3; role groups and named-tuple defaults stated as consequences, and mechanics
  their tickets record left to them (issue 85 one decision per ADR); the extension named
  `_wise_fsw_<configuration>` (issue 64 The F´ build on WiseDynamics' host module, one extension
  per configuration); parity compares GNC telemetry and the GNC command log, and a build's
  parameter values are checked by its own boot tests (issue 66 Parity is an analyzer over run
  files).
- **rev 1** — 2026-11-13 — first written (issue 37 the dictionary; issue 38 commands into the F´
  build).

## Context

One ground commands either build, records the telemetry either build writes, and the same analyzers
judge both. An algorithm flies in Python before any F´ build of it exists, with no compiler. The F´
build runs inside Basilisk with nothing on a thread of its own (ADR 0003 rev 4), and each build has
its own CDH (ADR 0005 rev 2).

At `6f6276e`, the Python build imitated F´'s wire format: it decoded F´ command packets, imitated
F´'s responses and packed telemetry into F´'s types. That is a Python version of F´ written as
glue. Flying the F´ build with F´'s real ground data system must stay possible, so names and
values never move inside `_wise_fsw_<configuration>`, the generated dictionary JSON stays, and
telemetry leaves through F´'s telemetry ports.

### The checks

They ran on branch `spike/two_edges` against main `6f6276e`, F´ v4.4.2, fpp 3.4.0.

**Native `fpp to-json`: PASS** (`8c83a2a`, `spikes/fpp/`). The native binary, with no Java, gives
the instances, connections with port numbers, constants and `@` annotations, through a topology that
imports a GNC sub-topology. `fprime_fpp/fpp to-json -d out fpp/Gnc.fpp fpp/Top.fpp`, exit 0, 0.01 s
on the scratch model; `python3 -I reader.py out`, condensed:

```
instances:   Gnc.nav:Nav  Gnc.ctrl:Ctrl  Gnc.log:Log  Gnc.rg:RateGroup  Top.drv:Driver
constants:   navDivider 1  ctrlDivider 10  tickHz 100  gain 2.5  name "gnc"
Top.Deploy:  Gnc.rg.RateGroupMemberOut[0] -> Gnc.nav.schedIn[0]   (and [1] ctrl, [2] log)
annotations: "provides: SRS010 free text, with spaces", "post-annotation on instance nav"
```

A missing imported group, an unresolved port number or a lost annotation would have shown in
`Top.Deploy`'s connections or the annotation list. Not covered: real F´ components (the components
were scratch ones), auto-numbered port arrays, and types, struct member order and parameter entries.

**`fprime-prm-write` and stock PrmDb: PASS** (`9eccec3`, `spikes/fprime/`). F´'s tool turns a case's
JSON into the `.dat` stock PrmDb loads at boot. `fprime-prm-write dat prm/nav_case.json -d
SpikeTopologyDictionary.json`, then `python spike_check.py b prm/nav_case.dat`. The JSON form it
takes is `{"<deployment>.<instance>": {"<param>": value}}`:

```
PrmFileLoadComplete : Parameter file load completed. Database: ACTIVE, Records: 2 (2 added and 0 updated).
nav.mu 398600441800000.0 valid
nav.dcm_PB [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]] valid
```

With the file missing, PrmDb reports `PrmFileReadError` and both parameters stay invalid, so a load
that failed would have shown. Not covered: this deployment's dictionary; the check used a scratch
deployment's.

**boot(prm_path): PASS** (`9eccec3`, `spikes/fprime/`). Setup moves out of import into
`boot(prm_path)`, and PrmDb reads the case's file there. `python spike_check.py b <case>.dat` from
two processes with two files: each read its own case's `mu`, so a path that never reached PrmDb
would have shown as equal values.

## Decision

### RadioEdge speaks F´'s vocabulary, and only the F´ build sees packets

- **The ground speaks names and values:** `<instance>.<entry>` names, values in FPP types, and
  `Fw.CmdResponse` codes, on both builds.
- **The F´ ground station in `ground/` does the GDS's job:** names to F´ command packets, and
  telemetry bytes to values. Real F´ packets exist only between it and
  `_wise_fsw_<configuration>`.
- **The Python build takes names directly**, and its CDH dispatches by name.
- **The F´ build dispatches through F´'s stock `Svc.CmdDispatcher`, unmodified,** on a task with no
  thread, run on the tick.

### Telemetry is pushed, and typed after the run

- **Every telemetry write is logged with the flight software's time tag, in the order written.**
  Nothing on the sim side samples or decimates it.
- **The recorder keeps the raw downlink during the run, packed,** and types it with the dictionary
  after it. The F´ build's downlink is F´'s own `TlmPacket`s, so a stock comm stack can replace the
  tap; the Python build logs each component's telemetry tuple once a frame.
- **A vector or quaternion is one channel of an array type**, written in one write.

### FPP is the contract

- **Both builds fly one FPP model:** types, role groups, commands, telemetry, parameters, capability
  claims, and each configuration's GNC sub-topology with its wiring and rates.
- **A rate is an FPP constant in the GNC sub-topology**, not F´'s C++ configuration alone, which
  the Python build cannot read.
- **A role is an instance name**, so an entry reads `<role>.<entry>` in every build.
- **F´'s generated JSON dictionary is the model's published form, and what the ground consumes.** A
  Python build's dictionary is generated from FPP alone with `fpp-to-dict`.
- **Python reads FPP's model through the native `fpp to-json`, in one module**, called directly,
  since F´'s wrapper sends `to-json` to Java. A contract test on the real flight software's FPP holds
  its shape and runs without an F´ build.
- **Each build's CDH is generated from FPP** through that module, with no compiler and no F´ build.
- **FPP types are generated named tuples in Python:** one per struct, and per algorithm its outputs,
  telemetry and parameters.

### Parameters: JSON per case, F´'s tool makes the `.dat`

- **The case's parameter record is JSON**, written by the ground from each algorithm's
  `parameters(scenario, vehicle)`. The Python build reads it.
- **F´'s `fprime-prm-write` makes the `.dat` from it**, which stock PrmDb loads at boot. None of
  this repository's code parses or writes F´'s binary parameter format.
- **A load that leaves any parameter invalid fails the case.**

### Parity is an analyzer whose spec is a minimum

- **Parity is an analyzer over run files**, with a stated reason for each tolerance.
- **It compares GNC telemetry and the GNC command log: every command sent to a GNC component.**
  The parameter values a build holds are checked by its own boot tests. A build may add anything
  beyond that, and extras are never compared.

## Alternatives considered

- **The Python build speaking F´ packets.** It keeps F´'s codec inside the Python
  build: a Python version of F´. Rejected for names at the ground and a ground station for the F´
  build.
- **`fpp to-layout` in place of the reader.** Named as the fallback, not taken. Its instance names
  are unqualified and it carries no types, constants or annotations, so it could replace only the
  connections. It stays the fallback if the JSON shape churns.
- **`to-json` through F´'s wrapper.** It needs Java 25. Rejected for the native binary.
- **A Python writer and reader for F´'s binary parameter format.** It brings F´'s codec back into the
  Python build and duplicates F´'s own tool. Rejected for JSON plus `fprime-prm-write`.
- **The Python build taking `parameters(scenario, vehicle)` directly, with a file only for F´.** The two
  builds would then not read one case record. Rejected.
- **An algorithm's configuration on an F´ port, sent at boot by the sim glue.** It is per-algorithm
  glue outside the FPP contract, and parity cannot see it. Rejected for F´ parameters.
- **Parity over every command and every channel.** F´ generates commands the Python build lacks and
  gives no refusal reason, so the logs would never match. Rejected for a minimum spec.
- **Dictionaries for inputs, outputs, telemetry and parameters.** A misspelled key passes silently.
  Rejected for named tuples.
- **A hand-written passive dispatcher, or the stock one drained from outside.** The first
  reimplements F´'s responses and drifts; the second is impossible, since `CommandDispatcherImpl` is
  `final` and its dispatch protected. Rejected.
- **Commands and telemetry declared in Python, with FPP generated at port time; or a Python build
  reading the F´ build's dictionary.** The first moves the contract's source at port time; the second
  needs a compiler before an algorithm flies in Python. Rejected.
- **Each vector component as a scalar channel.** A quaternion over four channels is not one write.
  Rejected.
- **Telemetry sampled on the simulation's recording grid.** It lets the sim set the rate and lose
  writes. Rejected.
- **A raw tuple per write across the edge.** Its cost showed in the per-case profile: measured on
  main at 3e5e95d (issue 122), the mean over 460 F´ and 460 Python Leo500 cases of the dead
  reckoner's parity notebook, flown in one process, was 35.7 ms per case in the F´ build's
  end-of-run drain and 25.6 ms in the Python link's per-field logging. Rejected for a packed
  downlink.
- **FSW telemetry in Basilisk message structs.** It limits the FSW to fields Basilisk defines.
  Rejected.

## Consequences

- The Python build holds no F´ codec. The F´ ground station is the only Python code that knows F´'s
  packets, and it is the part a real GDS replaces.
- A ported algorithm's F´ test asserts that its Python build's dictionary entries equal the F´
  build's, IDs aside, so a stale F´ build fails it.
- `to-json`'s layout is unversioned compiler internals, so an `fprime-fpp` bump that moves it fails
  the contract test on its Renovate PR and never mis-wires the Python build.
- Adding a channel or command while prototyping is two edits: the `.fpp` line and the Python that
  writes or handles it.
- Generating a Python build's dictionary takes 0.1–0.3 s, once per process for each model.
- A role's entries are `.fppi` groups a component includes, since `fpp-check` rejects `telemetry`
  in an FPP `interface`.
- Telemetry and outputs default to not written, and a parameter has no default unless its FPP
  declaration gives one, so a missing parameter fails both builds alike.
- Reopened if an F´ release drops the cooperative task routine, a component needs to block, a
  consumer needs one vector component written apart.
