# 0007 — Compile the F´ flight software with the settings flight standards ask for

**Status:** accepted
**Decided:** 2026-11-24 (issue 125 Build the F´ flight software to flight standards: every warning on and none left, and choose its analyzers)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-24 — first written (issue 125 Build the F´ flight software to flight standards:
  every warning on and none left, and choose its analyzers).

## Context

Flight standards treat the compiler as the first check on flight code. The Power of 10, rule 10,
asks for every warning at the compiler's most pedantic setting and none left, from the first day;
the JPL C standard's rule 2 asks the same, and asks for the code to be rewritten when a warning is a
false one. The rest is a language subset and settings that make the build the same wherever it is
built. A setting a standard or the compiler's own documentation recommends is taken; one is left out
only with its reason, in the Decision.

## Decision

**The flight C++ adopts JSF AV C++, the Power of 10, the JPL C standard and F´'s own C++ rules as
its coding standards.** They are the direction all of it is written to, held by the settings below
and by the analyzers (ADR 0008 rev 1).

| Setting | Why, and who states it |
|---|---|
| Every warning the compiler offers, each at its strictest level, as errors | Power of 10 rule 10, JPL rule 2 |
| Conversions that lose information, sign changes, double promotion, exact float comparison | JSF AV 180 and 202 |
| C-style casts | JSF AV 185 |
| Enumerations in switches, duplicated branches, missing declarations, undefined macros, shadowing, unused parameters | Power of 10 rule 10 |
| Exceptions off | JSF AV 208; F´ CPP-25 |
| RTTI off | F´ CPP-25 |
| Static guards off | One thread runs the deployment (ADR 0003 rev 4), so a function-local static has one initialiser |
| Floating-point contraction off | It would let the same source give different numbers on another build |
| Warnings about allocation, with fixed-size storage for what they name | JPL rule 5, JSF AV 206, Power of 10 rule 3 |
| Stack protector, stack-clash protection, control-flow protection, fortified libc, library assertions, zeroed variables, strict flexible arrays and padding | the OpenSSF compiler guide and gcc's own hardened set; stated so that every host compiles the same code |
| Linker warnings as errors; read-only relocation, immediate binding, no executable stack | the same |
| CMake deprecations as errors | Power of 10 rule 10, taken to the build itself |

- **The code written and generated here is held to every setting. F´'s library and FPP's output are
  held to F´'s own set.** What they can't meet is suppressed by name and place, with the reason
  written beside it.
- **Test equipment is outside it.**

A setting not taken, and why:

| Setting | Reason |
|---|---|
| `-Waggregate-return`, `-Wmultiple-inheritance`, `-Wnamespaces`, `-Wtemplates`, `-Wpadded` | They report what the code is made of, not a fault in it |
| `-Wabi-tag` | It reports the ABI tag of a standard library type, not a fault |
| `-Wsuggest-attribute=const`, `=pure`, `=cold`, `=malloc`, `=format`, `=returns_nonnull` | They ask for GNU attributes, outside ISO C++ (JSF AV 8) |
| `-fno-delete-null-pointer-checks`, `-fno-strict-aliasing`, `-fno-strict-overflow` | Each switches off a warning taken above that finds the fault |
| `-fno-use-cxa-atexit` | gcc's manual says the default is required for standard-conforming static destruction (JSF AV 8) |
| `-z nodlopen` | Python loads the extension |
| `-fanalyzer` | An analyzer (ADR 0008 rev 1) |

## Alternatives considered

- **F´'s own warning set alone.** It leaves out what the standards ask beyond it. Rejected.
- **A chosen subset of the compiler's warnings.** Each one left out needs a reason, and a warning
  held back is one nobody sees the findings of. Rejected.
- **MISRA C++ as a coding standard.** Its text is sold; JSF AV C++ and the JPL C standard build on
  MISRA's C guidelines. Rejected.
- **AUTOSAR C++14.** An automotive standard, superseded by MISRA C++. Rejected.
- **Turn the warnings on one at a time as the code is cleaned.** The compiler is the first check on
  flight code, and the Power of 10 asks for it from the first day. Rejected.
- **Hardening left to each host's compiler.** Hosts turn on different sets by default, so the same
  source would be built differently. Rejected.
- **Hardening off, for its cost in a tick.** Flight code is fast because it is well written.
  Rejected.
- **Freestanding C++, to take the heap away.** Eigen does not build under it, nor do parts of F´'s
  host platform. Rejected.
- **A lower optimisation level.** No adopted standard asks for one. Rejected.

## Consequences

- A new component meets every setting without listing them, and a warning fails the build.
- `-ffp-contract=off` holds the arithmetic the same when a build gains fused multiply-add.
