# 0006 — Meet the sim as a hardware-in-the-loop rig, on bus bytes

**Status:** accepted
**Decided:** 2026-11-14 (issue 51 two edges design; issue 52 tooling checks)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-14 — first written, moved out of ADR 0003 rev 3 (issue 85 one decision
  per ADR); the bus driver, named SimHub at `9eccec3`, is LabBusDriver, named for its job, and
  F´'s Svc.GenericHub is a rejected alternative, from the spike in the decision comment of
  2026-11-16 on issue 63 The lab's bus driver carries bus data into the F´ build.

## Context

The F´ build flies inside Basilisk's process (ADR 0003 rev 3). The lab is the test rig between
that build and the sim: the bus structs, the bus emulator, the stand-ins inside `_wise_fsw` and
the pins that move bytes in and out of it. The sim this repository plugs into,
WiseDynamics' FSW host, gives a build Basilisk messages by role and takes actuator commands back by
role. Real flight software meets its hardware through a bus driver that takes bytes. At `6f6276e`,
the F´ build's glue to the sim was wired by hand for one algorithm, so every added algorithm or
sensor needed C++ in the bridge and the pins.

### The check

The bus-driver check ran on branch `spike/two_edges` against main `6f6276e`, F´ v4.4.2, fpp 3.4.0,
pybind11 3.1.0.

**A bus driver on F´ serial ports: PASS** (`9eccec3`, `spikes/fprime/`). Bytes Python's
`struct.pack` writes for a bus struct equal F´'s serialization, and the bus driver delivers them as
the typed struct. `python spike_check.py a`:

```
python struct.pack: 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
F´ serializeTo    : 0000001cbe991a083f847ae147ae147bbf947ae1…40239d013a92a305
push status 0 -> imuSink got 1 123456789000 [0.01, -0.02, 0.03] [1.5, -2.25, 9.80665]
little-endian push decodes as 583948143490498560 [7.688e+284, …]
```

The little-endian push is the failure the comparison would have shown.

## Decision

- **If a real F´ deployment would have it, it is inside `_wise_fsw`.** Each stand-in replaces one
  real thing: LabBusDriver the bus driver, GroundLink the whole comm stack, SimTime the clock, its
  time source and its timer. Anything a real deployment would not have is ground segment
  (ADR 0004 rev 2) or the lab's own; the lab's pins are compiled in as a test connector.
- **Bus structs in FPP mirror Basilisk messages**, each held to the real message by a test.
- **A bus emulator, generated from the bus structs, turns Basilisk messages into their bytes.**
- **LabBusDriver takes the bytes on F´ `serial` ports** and delivers typed bus structs.
- **No part of the lab, and no sim glue, names an algorithm.**

## Alternatives considered

- **Typed ports in place of LabBusDriver.** Named as the fallback, not taken: the bus-driver check
  passed, and a real bus driver takes bytes.
- **Per-algorithm sim glue, as at `6f6276e`.** Every added algorithm or sensor needs C++ in the
  bridge and the pins. Rejected.
- **F´'s Svc.GenericHub in place of LabBusDriver.** FPP 3.4.0 writes serial-to-typed port calls
  with unqualified serializer names, so a hub outside module Bus does not compile. It also needs a
  buffer manager, an allocator and its own hub-to-hub framing, and its source shows it would pass
  a long push silently and drop a wrong port silently. Rejected (the spike in the decision comment
  of 2026-11-16 on issue 63 The lab's bus driver carries bus data into the F´ build).

## Consequences

- An added sensor is a bus struct and FPP wiring; no sim glue is written for it.
- The bus structs are a hand-kept mirror of Basilisk's messages; a test fails when one drifts.
