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
only where it breaks the build, switches off a warning already taken, or departs from standard C++,
and then the reason is here.

## Decision

**The flight C++ adopts JSF AV C++, the Power of 10, the JPL C standard and F´'s own C++ rules as
its coding standards.** They are the direction all of it is written to, held by the settings below
and by the analyzers (ADR 0008 rev 1).

| Setting | Why, and who states it |
|---|---|
| Warnings as errors: F´'s own set over everything; every other warning gcc offers that what is generated here meets, at its top level, over what is written and generated here; and the rest over what is written here, our generators' output included | Power of 10 rule 10, JPL rule 2; F´ applies its set to its own test deployments |
| Conversions that lose information, sign changes, double promotion, exact float comparison | JSF AV 180 and 202 |
| C-style casts | JSF AV 185 |
| Enumerations in switches, duplicated branches, missing declarations, undefined macros, shadowing, unused parameters | Power of 10 rule 10 |
| Exceptions off | JSF AV 208; F´ CPP-25 |
| RTTI off | F´ CPP-25 |
| Static guards off, floating-point contraction off | F´ ports turn the guards off; contraction would let the same source give different numbers on another build |
| Warnings about allocation, with fixed-size storage for what they name | JPL rule 5, JSF AV 206, Power of 10 rule 3 |
| Stack protector, stack-clash protection, control-flow protection, fortified libc, library assertions, zeroed variables, strict flexible arrays and padding | the OpenSSF compiler guide and gcc's own hardened set; stated so that every host compiles the same code |
| Linker warnings as errors; read-only relocation, immediate binding, no executable stack | the same |
| CMake deprecations as errors | Power of 10 rule 10, taken to the build itself |

- **The hand-written code, the generated code and F´ are all compiled this way**, but for the
  warnings the table limits. F´'s and FPP's headers, Eigen and pybind11 are system headers to the
  hand-written code. A diagnostic raised by F´'s library or FPP's output is suppressed by the name
  of its flag and its place, with the reason written beside it.
- **The pins are test equipment.** Both halves keep exceptions, which pybind11 and the assert hook
  need; the pybind11 half also keeps the RTTI and static guards pybind11 needs. The other half is
  compiled as flight code and takes no F´ class across its boundary, so the flight software is built
  without RTTI. What a flight wrote is held in memory that grows, so an allocation there is no
  warning.

## Alternatives considered

- **Turn warnings on one at a time, as they are fixed.** A setting held back is one nobody sees the
  findings of. Rejected.
- **Leave hardening to the distribution.** One host's compiler has it on by default and another's
  does not, so the same source would be built differently. Rejected.
- **Skip the hardening because it costs time.** Flight code is fast because it is well written, not
  because a protection is off. Rejected.
- **`-Waggregate-return`, `-Wmultiple-inheritance`, `-Wnamespaces`, `-Wtemplates`.** They report
  what the code is made of: functions returning values, `Cooperative`'s two F´ interfaces, F´'s
  namespaces, and `Rk4`'s template. Rejected.
- **`-Wpadded`.** It reports the layout of structs the compiler pads. Rejected.
- **`-Wabi-tag`.** It reports functions whose `std::string` carries an ABI tag, which the generated
  pins return. Rejected.
- **`-Wsuggest-attribute=const`.** It asks for a GNU attribute on constant functions, outside ISO
  C++ (JSF AV 8). Rejected.
- **`-fno-delete-null-pointer-checks`, `-fno-strict-aliasing`, `-fno-strict-overflow`.** Each
  switches off a warning above that finds the fault: `-Wnull-dereference` and `-Wstrict-aliasing`,
  measured with gcc 15.3, and `-Wstrict-overflow`, as gcc's manual says. Rejected while the warning
  holds.
- **`-fno-use-cxa-atexit`.** It builds and loads here, and the telemetry is the same. JSF AV 8 asks
  for conforming ISO C++, and gcc's manual says the default is required for fully
  standards-compliant handling of static destructors. Rejected.
- **`-z nodlopen`.** Python loads the extension. Rejected.
- **`-fanalyzer`.** An analyzer, rejected in ADR 0008 rev 1.
- **Freestanding.** Eigen does not build under it, nor do parts of F´'s host platform. Rejected.
- **A lower optimisation level.** No standard read asks for one. Rejected.

## Consequences

- A new component meets every setting without listing them, and a warning fails the build.
- The build needs gcc 15, for `-fzero-init-padding-bits=all`, on x86, for `-fcf-protection`.
- A compiler update can add warnings and fail the build; the compiler is not pinned here.
- The two compilers that build this, on a development host and in CI, may disagree about a warning,
  so both must pass.
- `-ffp-contract=off` holds the arithmetic the same when a build gains fused multiply-add.
