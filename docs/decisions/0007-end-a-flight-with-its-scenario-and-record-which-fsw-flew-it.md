# 0007 — End a flight with its scenario, and record which FSW flew it

**Status:** accepted
**Decided:** 2026-11-12 (issue 31 F´ in Basilisk)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-14 — moved out of ADR 0003 rev 2 (main at `6f6276e`), which carried it
  from rev 1 (issue 85 one decision per ADR).

## Context

Either build flies the same missions, scenarios and cases, and the judge reads each flight's
`flight.json` (ADR 0002 rev 1). Two builds of one algorithm can fly at one repository commit, so
the judge's session has to tell them apart.

## Decision

- **A flight's end belongs to the scenario**, never to a fixed length. The simulator stops only on
  time, so the one stopping rule the harness binds is the TST definition's duration.
- **Each flight's `flight.json` records which FSW flew**, beside the facts ADR 0002 rev 1 records
  there for the judge. `fsw` is the FSW builder's name, and `build` is the build's identity:
  - for the F´ build, its host's name, `frameworkVersion` (the F´ tag) and `projectVersion`, read
    from the dictionary's metadata. `projectVersion` names the commit the extension was built
    from, with a `-dirty` suffix when built from an uncommitted tree;
  - for the Python build, its host's name.

## Alternatives considered

- **The build identity in run-file attributes.** It needs the simulator changed. Rejected.
- **The repository commit alone as the build identity.** It cannot tell two builds of one commit
  apart. Rejected.

## Consequences

- Two builds of one algorithm are told apart in the judge's session, even at one repository commit.
- A stale extension shows as a `projectVersion` that differs from the run file's
  `versions_caller_commit`.
- Each case merges `build` into `flight.json` atomically, without a lock, so `build` can rarely be
  missing from a flight that already has a crashed case; any later successful case restores it.
