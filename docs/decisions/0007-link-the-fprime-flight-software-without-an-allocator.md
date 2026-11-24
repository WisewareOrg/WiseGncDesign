# 0007 — Link the F´ flight software without an allocator

**Status:** accepted
**Decided:** 2026-11-24 (issue 125 Hold the F´ flight software's C++ to no allocation after
initialization)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-24 — first written (issue 125 Hold the F´ flight software's C++ to no
  allocation after initialization).

## Context

Flight software takes its memory while it initializes and none after it, as an ARINC 653 partition
does before it enters NORMAL: an allocation in a frame costs unbounded time, and can fail. F´'s own
guidance is the same. The rule covers all the C++ a frame can run: the components written here, the
code FPP generates and the F´ library code both reach. A `std::vector` grows and a `std::string`
appends with no allocation in the text of the code that does it, and most of the C++ that runs is
generated or the framework's, so reading or annotating the source cannot hold it.

## Decision

- **Each configuration's flight software is linked without an allocator as part of its build.** The
  link has no C++ library and no libc, only a named list of what flight software may call outside
  itself, so code that can allocate or call into the C++ library does not link, and the linker names
  the function that does.
- **F´ sizes what it sizes at initialization from one allocator, over fixed memory, which closes
  when initialization ends.** The first frame ends it; a use after that trips F´'s assert. It is the
  only allocator in what is linked.
- **What a flight fills is fixed before it starts, and an overflow trips F´'s assert; it never grows
  and never drops a write.**
- **The lab's pins are outside the link.** They are the test connector (ADR 0006 rev 1), where Python
  meets the deployment; the frame itself is inside.

## Alternatives considered

- **Declared effects, clang's `nonallocating` with `-Wfunction-effects`.** Every function a frame
  calls in another file must carry the attribute. FPP's generated code and F´'s library cannot be
  annotated here, so a frame that allocates nothing is refused as readily as one that does.
  Rejected.
- **A checker of the source: clang-tidy's `no-malloc` and `owning-memory`, or a MISRA-type
  checker.** It sees an allocation that is written out, not a container that grows, and not a library
  or a generator's code. Rejected.
- **A script reading the built objects' symbols.** It sees what the link sees, with a parser to keep
  beside the linker that already does it. Rejected.
- **The allocators wrapped while the flight software runs, so an allocation in a frame faults.** It
  sees only the paths a run takes. Wrapped by the extension's link alone it misses an allocation made
  inside the C++ library, which is shared with Python. Rejected for the code; closing F´'s one
  allocator is this idea where it is complete, since nothing else can allocate.
- **RealtimeSanitizer.** It needs clang's runtime loaded ahead of Python, and sees only the paths a
  run takes. Rejected.
- **A test that traces allocations over a flight.** It sees only the paths the test flies, so a new
  component is held only once something flies it. Rejected as the gate; it measures well.
- **Buffers reserved at initialization and left to grow.** A reserve is a hint: a longer flight
  allocates in a frame. Rejected.

## Consequences

- An allocation added to a component, to F´ or to what FPP generates fails the build, with no test to
  write and nothing to annotate.
- Flight C++ gives up what the C++ library provides outside its headers. A component that needs some
  of it must be given fixed memory instead.
- The link cannot see inside a listed libc function: one that allocates when called a certain way is
  held only by not being called so.
- The support the language needs is named, so a compiler that needs more fails the link until it is
  added.
- A flight longer than the lab sized it for asserts.
- Python code is not held by this decision.
