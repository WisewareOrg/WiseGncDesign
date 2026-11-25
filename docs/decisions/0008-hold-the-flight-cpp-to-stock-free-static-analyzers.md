# 0008 — Hold the flight C++ to stock, free static analyzers

**Status:** accepted
**Decided:** 2026-11-24 (issue 125 Build the F´ flight software as ARINC 653 would)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-24 — first written (issue 125 Build the F´ flight software as ARINC 653
  would).

## Context

The flight C++ adopts JSF AV C++, the Power of 10, the JPL C standard and F´'s own C++ rules as the
direction it follows (ADR 0007 rev 1).

Flight C++ has to be held to the rules flight projects write: no warnings, no heap after
initialization, no exceptions, no recursion, every return checked. A compiler warning does not see
most of them, and a rule nobody checks is a convention. The rules are those flight standards state:
JSF AV C++, MISRA C++, the JPL and Power of 10 rules. Most flight software is closed, so open-source
flight projects are examples and not the measure. The tools have to be free, both in CI and on a
development host, and ship the rule themselves. A check written here would be one more thing to
trust, so only rules the tools ship are used.

## Decision

The rules, from the standards that state them, and what holds each here:

| Rule | Stated by | Held by |
|---|---|---|
| No warnings at the most pedantic level, and no analyzer warnings | JPL rule 2, Power of 10 rule 10 | the compiler, as errors; clang-tidy, cppcheck, CodeQL |
| No heap after initialization | JPL rule 5, Power of 10 rule 3, JSF AV 206, F´ CPP-1, MISRA C++ 21.6.1 | static storage; CodeQL, clang-tidy |
| No exceptions | JSF AV 208, F´ CPP-25 | the compiler |
| No recursion | JPL rule 4, Power of 10 rule 1; JSF AV 119 with exceptions | clang-tidy, CodeQL |
| Every loop has a provable bound | JPL rule 3, Power of 10 rule 2, F´ CPP-34 | CodeQL |
| Every returned status is checked | JPL rule 14, Power of 10 rule 7, F´ CPP-32; JSF AV 115 for error information | CodeQL |
| Complexity is limited | JSF AV 3, NPR 7150.2D SWE-220 for safety-critical components | CodeQL |

- **Each tool is adopted alone, in the change that adds it and fixes what it finds**, so main never
  carries a finding. The order is the compiler, then clang-tidy, cppcheck, CodeQL and IKOS.
- **The compiler refuses what it can:** warnings as errors, no exceptions, linker warnings fatal,
  over our code, the generated code and F´. What F´, Eigen or pybind11 trips is suppressed by name
  with its reason.
- **clang-tidy runs in the build**, so a finding fails the build: F´'s own flight check (no
  recursion), the Clang analyzer, and the checks for raw `malloc` and `new`.
- **cppcheck runs on our own sources in CI**, with F´'s options.
- **CodeQL runs in CI:** the JPL rules F´ and cFS run, the JSF rules on heap and exceptions, and
  MISRA C++'s rule against dynamic memory. A finding on our code blocks the merge.
- **IKOS runs in CI last, once flight code is static.** It looks for out-of-range indexes, null and
  uninitialised values and integer faults, and it ignores floating point, so it does not check an
  algorithm's arithmetic. Its alarms are cleared in the change that adds it, by a fix or by IKOS's
  own `__ikos_assume`, whose reason is written beside it. It alone of these reported a null
  dereference put into the code on purpose, and it does not yet complete on the missions.
- **Static storage carries the no-heap rule.** No analyzer tells an allocation at initialization
  from one after it, and none sees a vector inside an array. The rule is that flight code uses
  fixed-size F´ types; code that does not is converted in the change that adds the check, and the
  analyzers check that nobody adds a container back. F´'s own allocation at initialization is
  allowed.

## Alternatives considered

- **Cobra, from JPL, with its Power of 10 and JPL rules.** It matches names in the text, so it does
  not see what a container allocates. Of what it found, CodeQL found all but a call to F´'s own
  allocator, which F´ makes at initialization. Rejected.
- **Infer.** It caught nothing the others missed. Rejected.
- **gcc's `-fanalyzer`.** It is documented for C only, and it crashes on an Eigen source here.
  Rejected.
- **AUTOSAR and MISRA C heap rules in CodeQL.** Run; they found fewer of the same calls than JSF and
  MISRA C++. Rejected.
- **SonarQube's free edition.** It has no C++ analyzer. Its cloud service needs an account and a
  token, and was not run. Rejected.
- **Frama-C, Splint and the C-only tools.** They do not read this C++. Rejected.
- **ESBMC, CBMC, KLEE and the verifiers.** They ship no rule against allocation, so the rule would
  be written here. Not run. Rejected.
- **Compiler modes: freestanding, linking without the C++ library or a heap, poisoned names.**
  Freestanding refuses Eigen and the hosted F´ platform whether or not anything allocates; a link
  with no heap refuses F´'s own allocation at initialization. Rejected.
- **Clang's function-effect attributes.** Every function a frame calls must carry one, including
  generated and F´ code. Rejected.
- **An allocator of our own, or a link that lists what flight code may call.** Tried, and not taken:
  a rule written here has to be checked here, and each needed more of our own code to check it.
  Rejected.
- **A review checklist alone.** F´ holds its own heap rule by review; a rule no tool checks depends
  on who looks. Rejected as the only means.

## Consequences

- A finding is fixed where it is found, or allowed by name with a reason; a suppression names the
  flag, the place and the reason; generated code and F´ carry the few they need.
- The analyzers disagree in places and repeat each other in others; each earns its place by what it
  alone reports.
- CodeQL is free here only while this repository is public and under an open-source licence.
- None of them proves that nothing allocates after initialization. A component that needs a
  container must be given a fixed size.