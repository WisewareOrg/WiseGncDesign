# 0001 — Judge Monte Carlo sessions with requirement analyzers

**Status:** accepted
**Decided:** 2026-11-09 (issue 27 requirement analyzers, ruled with the design of WiseDynamics issue 22
sim sessions)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-09 — first written (issue 27 requirement analyzers).

## Context

A Monte Carlo test checks each case against a bound, so nothing judges a requirement across cases.
A requirement is a statement about the ensemble: a share `p` of runs stay within `X`, shown at
confidence `c`. The same requirement applies to any navigation algorithm, so its analysis must not
be written into one algorithm's test, and a test must be able to claim several requirements.

## Decision

- **A requirement owns its analyzer.** One analyzer module per requirement under `analysis/` holds the
  requirement's ID, statement and limits and calls a metric from `gnc_analysis`. Every Monte Carlo
  test that claims the requirement reuses it, so any algorithm is judged by the same analysis.
- **Monte Carlo tests are tagged with the requirements they verify.** A `verifies` mark names
  requirement IDs, test to requirement, many-to-many. The tag is read from the test's source when
  judging, so the simulator knows nothing of requirements. This is the opposite direction to
  [WiseKiosk ADR 0005 rev 4](https://github.com/WisewareOrg/WiseKiosk/blob/main/docs/decisions/0005-traceability-gating.md),
  where the requirements tree gates the work: here the work declares what it verifies. The IDs are
  not fixed by this decision.
- **Judging is a separate pytest run after simulation, over one session.** It reads the runs a
  session holds and never re-simulates, so tagging a test that already has runs judges them.
- **A cell is a (requirement, test) pair.** It gets an allowed-failures verdict: the largest `k`
  such that `k` failures still show `p` at confidence `c` under the one-sided Clopper-Pearson test
  on `n` planned cases. If no `k` exists the cell is not judged. A requirement passes only when
  every claiming cell passes.
- **A missing case leaves its cell not judged**, naming the cases found and missing, rather than
  counting as a pass or a failure.
- **Evidence is kept in the session.** The verdict matrix and each requirement's plot are written
  beside the runs they judge.

Where requirements and their limits are stored is outside this decision; a later ADR decides it
without touching this one.

## Alternatives considered

- **The mark carries the analysis function.** The analysis would live with each test, so every
  algorithm re-states it and two tests claiming one requirement can disagree. Rejected: the analysis
  belongs to the requirement.
- **Allocating requirements to roles or builds.** Rejected: a test already says what it verifies,
  and a second allocation can only contradict it.
- **Pooling runs across tests.** One verdict over the union of runs hides a test that fails alone,
  and mixes populations with different scenarios. Rejected: each test's cell is judged on its own.
- **Tags recorded by WiseDynamics in the simulator's per-test record.** Rejected: it gives the simulator the concept
  of a requirement, and a tag added later would need a re-simulation.
- **Tags copied into run files.** Rejected for the same two reasons.
- **Hard-coding the test in the analyzer.** Rejected: the analyzer would serve one algorithm.
- **Discovering tests by data fit.** Choosing the tests whose runs contain the metric's data judges
  tests nobody claimed. Rejected: a claim is an explicit statement.
- **The verdict inside the Monte Carlo pytest session.** Rejected: the verdict would need every case
  in one session and could not be re-judged without re-simulating.

## Consequences

- Adding a requirement is adding an analyzer, and verifying it for another algorithm is adding a tag.
- Judging a session twice gives the same verdict, and the session holds what it was judged from.
- A cell needs every planned case before it is judged, so an interrupted campaign is reported as not
  judged rather than as a pass.
