# 0001 — Judge Monte Carlo sessions with requirement analyzers

**Status:** accepted
**Decided:** 2026-11-11 (issue 29 missions, which settled how a test claims a requirement and how a
missing case is counted)
**Rev:** 2

## Revisions

- **rev 2** — 2026-11-11 — three decisions superseded by ADR 0002 rev 1: the `verifies` tag, "a
  requirement owns its analyzer", and "a missing case leaves its cell not judged" (issue 29
  missions).
- **rev 1** — 2026-11-09 — first written (issue 27 requirement analyzers).

## Context

A Monte Carlo test checks each case against a bound, so nothing judges a requirement across cases.
A requirement is a statement about the ensemble: a share `p` of runs stay within `X`, shown at
confidence `c`. The same requirement applies to any navigation algorithm, so its analysis must not
be written into one algorithm's test, and a test must be able to claim several requirements.

## Decision

- **An analyzer is shared by every algorithm.** One analyzer module judges a requirement for every
  Monte Carlo test that claims it, so any algorithm is judged by the same analysis. Which
  requirements an analyzer judges is decided by ADR 0002 rev 1.
- **A test claims requirements, many-to-many.** The simulator knows nothing of requirements, and a
  requirement does not list the tests that claim it. How a test claims them is decided by ADR 0002 rev 1.
- **Judging is a separate pytest run after simulation, over one session.** It reads the runs a
  session holds and never re-simulates, so claiming a requirement for a test that already has runs
  judges them.
- **A cell is a (requirement, test) pair.** It gets an allowed-failures verdict: the largest `k`
  such that `k` failures still show `p` at confidence `c` under the one-sided Clopper-Pearson test
  on the `n` runs found. If no `k` exists the cell is not judged. A requirement passes only when
  every claiming cell passes.
- **A crashed case counts as one failed case.**
- **Evidence is kept in the session.** The report is written beside the runs it judges, organised
  by test: each claiming test's matrix and a plot per cell, and a rollup of requirement by test.

Where requirements and their limits are stored is decided by ADR 0002 rev 1.

## Alternatives considered

- **The test carries the analysis function.** The analysis would live with each test, so every
  algorithm re-states it and two tests claiming one requirement can disagree. Rejected: the analysis
  belongs with the metric, not with a test.
- **Pooling runs across tests.** One verdict over the union of runs hides a test that fails alone,
  and mixes populations with different scenarios. Rejected: each test's cell is judged on its own.
- **Hard-coding the test in the analyzer.** Rejected: the analyzer would serve one algorithm.
- **Discovering tests by data fit.** Choosing the tests whose runs contain the metric's data judges
  tests nobody claimed. Rejected: a claim is an explicit statement.
- **The verdict inside the Monte Carlo pytest session.** Rejected: the verdict would need every case
  in one session and could not be re-judged without re-simulating.

## Consequences

- A new algorithm is judged by the analyzers that already exist once it claims requirements, and a
  new requirement is an analyzer or a rung of one.
- Judging a session twice gives the same verdict, and the session holds what it was judged from.
- An interrupted campaign is judged on the cases that finished, and is reported as not judged only
  when they are too few to show `p` at `c`.
