# 0005 — Partition each build into RIO, CDH, GNC and platform, one frame per tick

**Status:** accepted
**Decided:** 2026-11-23 (issue 51 two edges design; issue 61 The Python frame runner, on
WiseDynamics' host module; issue 106 Profile the F´ build's per-case time)
**Rev:** 3

## Revisions

- **rev 1** — 2026-11-13 — first written (issue 52 tooling checks); FPP carries each sensor role's
  bus-to-GNC pairing, and the Python build's frame refuses delayed feedback and fan-out (issue 61
  The Python frame runner, on WiseDynamics' host module); F´ in a repository of its own rejected,
  moved from ADR 0003 rev 3 (issue 85 one decision per ADR); FPP pairs each actuator role too, its
  direction the reverse of a sensor's, and a configuration takes only the roles its GNC
  sub-topology exposes (issue 95 Generate the actuator direction and each configuration's role
  wiring, in both builds).
- **rev 2** — 2026-11-23 — the Python build copies a message's data once each way, in RIO, and CDH
  passes the arrays through, so a sensor input reaches GNC read-only (issue 87 Speed up the Python
  build's frame overhead).
- **rev 3** — 2026-11-23 — at the hardware edge a frame only copies: each build's RIO binds its
  buffers and payloads at boot or at the first tick, a tick allocates nothing there, and a sensor
  input is valid for its tick, so GNC copies what it keeps (issue 106 Profile the F´ build's
  per-case time).

## Context

The algorithms are written in Python first and flown with no F´ build, and F´ is good flight
software in its own right, not a mirror of the Python build. Each build meets the world at two
edges: the ground (ADR 0004 rev 3) and the sim (ADR 0006 rev 2).

At `6f6276e`, one object per build did bus I/O, unit conversion, commands, telemetry and the
algorithm, wired by hand for one algorithm. A second algorithm had no place to sit, and the glue grew
with every algorithm. Components should be semi-realistic all the
way through, partitioned as real flight software is.

## Decision

- **Each tick is one frame: RIO in, CDH in, GNC, CDH out, RIO out.**
- **Each build has the same four partitions:**
  - RIO does bus I/O;
  - CDH converts bus data to engineering units, dispatches commands, logs telemetry and loads
    parameters;
  - GNC runs the algorithms;
  - platform is the clock, the tick and the tasks.
- **GNC touches neither edge.**
- **At the hardware edge a frame only copies.** Every buffer and payload that carries a reading in
  or a command out is made at boot or bound at the first tick; a tick copies into it and allocates
  nothing. A sensor input is valid for its tick, as a sampling port's is: GNC copies what it keeps.
  ADR 0006 rev 2 holds the lab to the same rule.
- **Each build has its own CDH**, however thin.
- **FPP pairs each role's bus struct with the GNC's struct.** A CDH component,
  `Cdh.BusConverter` in `fsw/fpp/interfaces/`, has per role an input `<role>In` and an output
  `<role>Out`: a sensor's `<role>In` is typed by the bus struct and its `<role>Out` by the GNC's;
  an actuator's the reverse. FPP type-checks both ends, and each build's CDH reads the same
  declaration.
- **An algorithm's code lives in `algorithms/<name>/`, and GNC wires it in.** A configuration
  reaches its algorithms only through its GNC sub-topology.
- **RIO, CDH and platform name no algorithm**; ADR 0006 rev 2 holds the lab and the sim glue to the
  same rule.
- **RIO, CDH and platform live in `fsw/<build>/<partition>/`; GNC is one sub-topology in
  `fsw/fpp/gnc/` that both builds fly.** The Python frame runner is nothing but these partitions.

## Alternatives considered

- **One object per build doing every job, as at `6f6276e`.** A second algorithm has no place to
  sit, and each algorithm brings its own glue for bus I/O, conversion, commands and telemetry.
  Rejected.
- **An annotation on each bus struct naming its role and GNC struct.** FPP does not check it, so it
  is an annotation dialect the generators parse. Rejected for the CDH component's ports.
- **Pairing by name rules alone.** The F´ generator runs at build time with no vehicle to learn a
  role's payload from, so it cannot supply the F´ CDH. Rejected for the CDH component's ports.
- **One CDH converter shared by both builds.** One build would then run the other's internals, and
  a Python build must fly with no F´ build. Rejected for a CDH per build, each generated from the
  same FPP (ADR 0004 rev 3).
- **F´ in a repository of its own.** Each algorithm and its F´ build are written side by side.
  Rejected.
- **The Python build copying a message's data at every partition boundary, as F´ does.** Python
  passes references, so a second copy at CDH protects only memory no one keeps, at a per-tick cost
  that dominates the frame. Rejected for one copy each way, in RIO, with read-only sensor arrays.
- **A fresh read-only copy of each message every tick, as rev 2 had it.** Each tick allocates the
  copy, its views and its tuple: RIO-in's largest per-tick cost, about 39 ms of a 5,700-tick Leo500
  case. A held input that never changes also lets an algorithm keep what a real partition would
  have to copy. Rejected for a buffer per message, bound once and refreshed in place.

## Consequences

- A second algorithm joins a configuration in FPP, with no glue written for it in either build.
- A configuration takes only the roles its GNC sub-topology exposes; its role wiring is generated
  from those ports.
- Both builds have the same shape, so a reader of one can find their way in the other.
- The Python build's GNC refuses a backward edge (one-frame-delayed feedback) and an output feeding
  more than one input, until an algorithm needs either.
- The Python build converts each role's message twice per tick, Basilisk payload to bus struct in
  RIO and bus struct to GNC struct in CDH for a sensor, and back for an actuator, as the F´ path
  does. Unlike the F´ path, it copies the data once each way, in RIO: CDH passes the arrays through,
  so a sensor input reaches GNC read-only and an algorithm editing it in place raises.
- An algorithm that keeps a sensor input past its tick copies it; a held reference shows the next
  tick's values, as the F´ build's ports do.
- A test traces each build's RIO-in and RIO-out, and the lab's tick, with `tracemalloc` and holds
  them to no allocation per tick. It sees Python and numpy; F´'s C++ is held to it by its fixed
  buffers alone.
