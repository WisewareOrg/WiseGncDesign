# 0005 — Split each build into RIO, CDH, GNC and platform partitions, one frame per tick

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
grows with every algorithm. Components should be semi-realistic all the way through: a real flight
software's partitions, in both builds.

## Decision

- **Each tick is one frame: RIO in, CDH in, GNC, CDH out, RIO out.**
- **Each build has the same four partitions:**

  | Partition | Job | Python build | F´ build |
  |---|---|---|---|
  | RIO | bus I/O | `fsw/python/rio/` | `fsw/fprime/rio/` |
  | CDH | units, commands, telemetry, parameters | `fsw/python/cdh/` | `fsw/fprime/cdh/` |
  | GNC | the algorithms | `fsw/python/gnc/`, flying `fsw/fpp/gnc/` | `fsw/fpp/gnc/` and each algorithm's C++ |
  | Platform | clock, tick, tasks | `fsw/python/platform/` | `fsw/fprime/platform/` |

- **GNC touches neither edge, and each build has its own CDH**, however thin.
- **The Python frame runner is only those four folders.** Events, sequencing, health and data typing
  are not its job, and it builds fresh objects per case.
- **An algorithm lives in `algorithms/<name>/`**: its notebook, its `<Name>.fpp` and an optional C++
  component.
- **No file in the generic code names an algorithm:** `fsw/fprime/{cdh,rio,platform}/`,
  `fsw/python/{cdh,rio,platform}/` and `lab/`.
- **A configuration in `fsw/fprime/configurations/` is named for the configuration**, and reaches
  algorithms only through its GNC sub-topology in `fsw/fpp/gnc/`, never through an `algorithms/`
  path.

## Alternatives considered

- **One object per build doing every job, as in the baseline.** A second algorithm has no place to
  sit, and each algorithm brings its own glue for bus I/O, conversion, commands and telemetry.
  Rejected.
- **One CDH converter shared by both builds.** One build would then run the other's internals, and
  a Python build must fly with no F´ build. Rejected for a CDH per build, each generated from the
  same FPP (ADR 0004 rev 2).

## Consequences

- A second algorithm joins a configuration in FPP, with no glue written for it in either build.
- The algorithm-name rule is one grep over the generic folders, kept as a test.
- Both builds have the same shape, so a reader of one can find their way in the other.
