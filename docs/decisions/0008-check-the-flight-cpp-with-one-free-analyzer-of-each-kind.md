# 0008 — Check the flight C++ with one free analyzer of each kind

**Status:** accepted
**Decided:** 2026-11-25 (issue 125 Build the F´ flight software as ARINC 653 would)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-25 — first written (issue 125 Build the F´ flight software as ARINC 653
  would).

## Context

The flight C++ adopts JSF AV C++, the Power of 10, the JPL C standard and F´'s C++ rules as its
coding standards
([ADR 0007 rev 1](0007-compile-the-fprime-flight-software-with-the-settings-flight-standards-ask-for.md)).
The standards that could be read ask for an activity and for evidence that its results are acted on,
and name no tool. A NASA Engineering and Safety Center update on flight-termination software reports
that static analyzers find and miss different defects. The tools have to be free in CI and on a
development host.

## Decision

| Kind of check | Who asks for it | Tool |
|---|---|---|
| Compiler at every warning, none left | Power of 10 rule 10, JPL rule 2 | gcc (ADR 0007 rev 1) |
| Coding-standard checker | NASA SWE-061 and SWE-185, ECSS-Q-ST-80C 6.3.4, MISRA Compliance | CodeQL, with its JSF AV, JPL and Power of 10 rules and its coding-standards pack's MISRA C++ rules |
| Bug finder | NASA SWE-135; NASA's IKOS tutorial starts with a lightweight analyzer | clang-tidy, with the Clang analyzer, run in the build |
| Bug finder from another engine | the same NASA update, which says running several tools gives better results | cppcheck, with F´'s options |
| Sound check for run-time errors | ECSS-E-ST-40C 5.8.3.5 and its informative Annex U list the errors, without asking for soundness; the formal-methods supplement to DO-178C, read through a secondary source, is the route for it | IKOS |
| Review by people | NASA, JPL and MISRA | the pull-request review |

- **Each is adopted alone, in the change that adds it and fixes what it finds.** The order is
  clang-tidy, cppcheck, CodeQL, then IKOS, after the flight code holds no heap in a frame.
- **A finding on our code or generated code fails the check.** A suppression names the rule, the
  place and the reason.
- **IKOS is given the units whose inputs can be bounded**, and an alarm it cannot clear is cleared
  by its own assumption, with the reason written beside it.

## Alternatives considered

- **One analyzer.** NASA's Mars Science Laboratory used several, with little overlap among them, and
  a NASA verification study of other flight software found that no one tool covers everything.
  Rejected.
- **A commercial analyzer.** A NASA Engineering and Safety Center report recommends at least one,
  with a strict rule set on every build. The tools here are free. Rejected.
- **IKOS left out, for the alarms it raises and the floating point it ignores.** It is the only free
  sound analyzer read that takes C++. Rejected.
- **Infer and Cobra.** Infer is a bug finder, as clang-tidy and cppcheck are, and reported nothing
  they did not; Cobra checks patterns in the text. Rejected.
- **gcc's `-fanalyzer`.** gcc's manual says it is only suitable for use on C, and it crashes on an
  Eigen source here. Rejected.

## Consequences

- The tools repeat each other in places; a finding is fixed or suppressed with a reason once.
- CodeQL is free only while this repository is public, hosted on GitHub and under an open-source
  licence.
- None of these tools proves that heap is unused after initialization, or checks the whole of JSF AV
  C++, or comes with a DO-330 qualification package. Review and the coding standards cover what they
  can.
