# 0006 — Fetch F´ and Eigen by tag, with no git submodule

**Status:** accepted
**Decided:** 2026-11-12 (issue 31 F´ in Basilisk)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-14 — moved out of ADR 0003 rev 2, the rev on main, which carried it from
  rev 1 (issue 85 one decision per ADR).

## Context

The F´ build compiles against F´ and Eigen, neither of which is written in this repository. Each
needs a pinned version that a dependency bot can bump and that CI proves before it lands.

## Decision

- **F´ and Eigen are pinned by release tag and fetched by it, with no git submodule.**
- **Renovate bumps the tags.**
- **F´'s tag and the tools it pins arrive as one update**, which CI proves together.
- **A test holds the tools to the versions F´ pins.**

## Alternatives considered

- **F´ as a git submodule.** Renovate's submodule manager is off in the preset this repository
  extends, and it tracks commits, not release tags. Rejected.
- **Eigen as a tarball pinned by hash.** Renovate cannot recompute the hash when it bumps the
  version. Rejected.

## Consequences

- An F´ release bump arrives as one Renovate update with the tools F´ pins, and a tool pin that
  drifts from F´'s fails a test.
