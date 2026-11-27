# 0008 — Check the flight C++ with one free analyzer of each kind

**Status:** accepted
**Decided:** 2026-11-24 (issue 125 Build the F´ flight software to flight standards: every warning on and none left, and choose its analyzers)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-24 — first written (issue 125 Build the F´ flight software to flight standards:
  every warning on and none left, and choose its analyzers).

## Context

The coding standards the flight C++ adopts are in
[ADR 0007 rev 1](0007-compile-the-fprime-flight-software-with-the-settings-flight-standards-ask-for.md).
NASA's and ECSS's standards ask for an activity and for evidence that its results are acted on, and
name no tool. A NASA Engineering and Safety Center update on flight-termination software reports
that static analyzers find and miss different defects. The tools have to be free in CI and on a
development host.

## Decision

| Kind of check | Who asks for it | Tool |
|---|---|---|
| Compiler at every warning, none left | Power of 10 rule 10, JPL rule 2 | gcc (ADR 0007 rev 1) |
| Coding-standard checker | NASA SWE-061 and SWE-185, ECSS-Q-ST-80C 6.3.4, MISRA Compliance | CodeQL, with its JSF AV, JPL and Power of 10 rules; its MISRA C++ rules are checked, and MISRA C++ is not adopted as a standard (ADR 0007 rev 1) |
| Bug finder | NASA SWE-135; NASA's IKOS tutorial starts with a lightweight analyzer | clang-tidy, with the Clang analyzer |
| Bug finder from another engine | the same NASA update, which says running several tools gives better results | cppcheck |
| Sound check for run-time errors | ECSS-E-ST-40C 5.8.3.5 and its informative Annex U list the errors, without asking for soundness | IKOS |
| Review by people | NASA, JPL and MISRA | review |

A finding on our code or generated code fails the check. A suppression names the rule, the place and
the reason.

## Alternatives considered

- **One analyzer.** NASA's Mars Science Laboratory used several, with little overlap among them, and
  a NASA verification study of other flight software found that no one tool covers everything.
  Rejected.
- **A commercial analyzer.** A NASA Engineering and Safety Center report recommends at least one,
  with a strict rule set on every build. The tools have to be free. Rejected.
- **No sound analyzer, for the floating point IKOS ignores.** A bug finder looks for errors; a sound
  analyzer reports that there are none. Rejected.
- **Infer and Cobra.** Infer is a bug finder, as clang-tidy and cppcheck are; Cobra checks patterns
  in the text. Rejected.

## Consequences

- The tools repeat each other in places; a finding is fixed or suppressed with a reason once.
- CodeQL is free only while this repository is public, hosted on GitHub and under an open-source
  licence.
- Review and the coding standards cover what the tools do not.
