# 0005 — Partition each build into RIO, CDH, GNC and platform, one frame per tick

**Status:** accepted
**Decided:** 2026-11-13 (issue 51 two edges design)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-13 — first written (issue 52 tooling checks).

## Context

The algorithms are written in Python first and flown with no F´ build, and F´ is good flight
software in its own right, not a mirror of the Python build. Each build meets the world at two
edges: the ground (ADR 0004 rev 2) and the sim (ADR 0003 rev 3).

In the baseline build, one object per build does bus I/O, unit conversion, commands, telemetry and
the algorithm, wired by hand for one algorithm. A second algorithm has no place to sit, and the glue
grows with every algorithm. Components should be semi-realistic all the way through, partitioned as
real flight software is.

## Decision

- **Each tick is one frame: RIO in, CDH in, GNC, CDH out, RIO out.**
- **Each build has the same four partitions:**
  - RIO does bus I/O;
  - CDH converts bus data to engineering units, dispatches commands, logs telemetry and loads
    parameters;
  - GNC runs the algorithms;
  - platform is the clock, the tick and the tasks.
- **GNC touches neither edge.**
- **Each build has its own CDH**, however thin.
- **An algorithm's code lives in `algorithms/<name>/`, and GNC wires it in.** A configuration
  reaches its algorithms only through its GNC sub-topology.
- **RIO, CDH, platform and the lab name no algorithm.**
- **A partition lives in `fsw/<build>/<partition>/`**, and the Python frame runner is nothing but
  these partitions.

## Alternatives considered

- **One object per build doing every job, as in the baseline.** A second algorithm has no place to
  sit, and each algorithm brings its own glue for bus I/O, conversion, commands and telemetry.
  Rejected.
- **One CDH converter shared by both builds.** One build would then run the other's internals, and
  a Python build must fly with no F´ build. Rejected for a CDH per build, each generated from the
  same FPP (ADR 0004 rev 2).

## Consequences

- A second algorithm joins a configuration in FPP, with no glue written for it in either build.
- Both builds have the same shape, so a reader of one can find their way in the other.
