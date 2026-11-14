# 0004 — Hold both builds to one FPP contract, spoken in F´'s names

**Status:** accepted
**Decided:** 2026-11-13 (issue 51 two edges design; issue 52 tooling checks)
**Rev:** 2

## Revisions

- **rev 2** — 2026-11-13 — retitled from "Carry commands and telemetry in F´'s form, from one FPP
  dictionary" and rewritten to two edges: RadioEdge in F´'s names, the F´ ground station, typing
  after the run, FPP as the contract read through the native `fpp to-json`, the generator and its
  named tuples, parameter files, and parity as an analyzer; with the checks' results (issue 52
  tooling checks).
- **rev 1** — 2026-11-13 — first written (issue 37 the dictionary; issue 38 commands into the F´
  build).

## Context

One ground commands either build, records the telemetry either build writes, and the same analyzers
judge both. An algorithm flies in Python before any F´ build of it exists, with no compiler. The F´
build runs inside Basilisk with nothing on a thread of its own (ADR 0003 rev 3).

In the build of main at `6f6276e`, the Python build imitates F´'s wire format: it decodes F´ command
packets, imitates F´'s responses and packs telemetry into F´'s types. That is a Python version of F´
written as glue. Flying the F´ build with F´'s real ground data system must stay possible, so names
and values never move inside `_wise_fsw`, the generated dictionary JSON stays, and telemetry leaves
through F´'s telemetry ports.

## Decision

### RadioEdge speaks F´'s vocabulary, and only the F´ build sees packets

- **The ground speaks names and values:** `<instance>.<entry>` names, values in FPP types, and
  `Fw.CmdResponse` codes. Its procedure runner has `send`, `tlm`, `until` and `truth`.
- **The F´ ground station in `ground/` does the GDS's job:** names to F´ command packets, and
  telemetry bytes to values. Real F´ packets exist only between it and `_wise_fsw`.
- **The Python build takes names directly.** Its CDH dispatches by name: an unknown name answers
  `INVALID_OPCODE`, and a `ValueError` answers `VALIDATION_ERROR` with its message.
- **The F´ build dispatches through F´'s stock `Svc.CmdDispatcher`, unmodified,** on `Os_Task_Sim`,
  an `Os::Task` with no thread. The tick runs every queue until it is empty, so a command uplinked
  before a step runs at that step.

### Telemetry is pushed, and typed after the run

- **Every telemetry write is logged with the flight software's time tag, in the order written.**
  Nothing on the sim side samples or decimates it.
- **The recorder keeps raw writes during the run** and types them into their FPP types with the
  dictionary after it. A live `tlm()` decodes on demand.
- **A vector or quaternion is one channel of an array type**, written in one write.

### FPP is the contract

- **Both builds fly one FPP model:** ICD types, bus structs, role groups, commands, telemetry,
  parameters, capability claims (`@ provides: SYS…`), and each configuration's GNC sub-topology with
  its wiring and rates (ADR 0003 rev 3).
- **F´'s generated JSON dictionary is the model's published form.** A Python build's dictionary is
  generated from FPP alone with `fpp-to-dict`, against the F´ source clone, into a temp dir.
- **Python reads FPP's model through the native `fpp to-json`,** called directly, since F´'s wrapper
  sends `to-json` to its Java JAR. One module parses the output and extracts only instances,
  connections, port numbers, constants and annotations. A contract test on the real flight
  software's FPP, added by issue 55 read FPP's model in Python, fails loudly if an `fprime-fpp` bump
  changes the shape. It needs only the native `fpp`, so it runs without an F´ build and never skips,
  and a breaking bump fails on its Renovate PR.

### The generator and its named tuples

- **`fsw/codegen/` generates each build's CDH from FPP**, read with the native `fpp`, with no
  compiler and no F´ build. Fields map by name, ignoring case, and a missing ICD field fails (issue
  58 CDH generator, Python half). It makes the Python converters at import, into a temp dir; the F´
  CDH component when CMake calls it; and the bus emulator's serializers.
- **Every FPP struct is a generated named tuple in Python:** arrays as numpy arrays, scalars as
  numbers, enums by name; immutable, and passable field by field into numba.
- **Each algorithm's outputs, telemetry and parameters are generated named tuples too**, e.g.
  `NavOutputs`, `NavTelemetry`, `NavParameters`. `step(t, <one argument per input>)` and command
  handlers return `NavOutputs(…), NavTelemetry(…)`, and `parameters(scenario)` returns
  `NavParameters(…)`. Every field defaults to not written, so a channel written only at some ticks
  stays honest, and a misspelled field fails at once.
- **Convention lookups fail loudly:** a component with no Python class, or a `@ provides` claim the
  requirements tree does not hold, is an error (issue 65 missions name a GNC sub-topology and a
  build).

### Parameters: JSON per case, F´'s tool makes the `.dat`

- **The ground's parameter-file writer emits each case's values as JSON**, from each algorithm's
  `parameters(scenario)`, in the form F´'s `fprime-prm-write` takes. That tool writes the `.dat`
  that stock PrmDb loads at boot, and the Python build reads the JSON. Both files are saved beside
  the run file.
- **`fprime-gds`, pinned by F´ v4.4.2 at 4.4.0, joins the uv environment.** No Python code parses or
  writes F´'s binary parameter format.
- **PrmDb's sandbox root is the directory that holds the case's parameter file**, derived in the
  boot pin from the one absolute `prm_path`. PrmDb refuses every open until a sandbox is configured.

### Parity is an analyzer whose spec is a minimum

- **Parity is an analyzer in `analysis/` over run files**, with a stated reason for each tolerance
  (issue 66 parity is an analyzer over run files).
- **It compares GNC telemetry, parameter values, and the command log of every command sent to a GNC
  component:** time sent, name, arguments, response code and response time.
- **A build may add anything beyond that, and extras are never compared:** free-text reasons,
  commands only one build has (F´'s `_PRM_SET`, `CMD_NO_OP`), and telemetry about other partitions or
  process health (`cmdDisp.*`, `prmDb.*`).

## Results

The checks ran on F´ v4.4.2 and `fprime-fpp` 3.4.0, on branch `spike/two_edges`.

### Native `fpp to-json`: PASS (commit `8c83a2a`, `spikes/fpp/`)

A scratch deployment topology `Top.Deploy` imports a GNC sub-topology `Gnc.Gnc` with a three-member
rate group, constants and `@` annotations.

```
$ fprime_fpp/fpp to-json -d out fpp/Gnc.fpp fpp/Top.fpp      # exit 0, Java not installed
$ python3 -I reader.py out          # reader-output.json, condensed
instances:   Gnc.nav:Nav  Gnc.ctrl:Ctrl  Gnc.log:Log  Gnc.rg:RateGroup  Top.drv:Driver
constants:   navDivider 1  ctrlDivider 10  tickHz 100  gain 2.5  name "gnc"
Top.Deploy:  Gnc.rg.RateGroupMemberOut[0] -> Gnc.nav.schedIn[0]   (and [1] ctrl, [2] log)
annotations: "provides: SRS010 free text, with spaces", "post-annotation on instance nav"
```

Wall time is 0.01 s on the scratch model, and 0.17 s on the deployment of main at `6f6276e`. The
connections reached only through the import, with their port numbers, are in `Top.Deploy`.
`reader.py`, 57 lines, is the proof that one module parses it.

**Where the data is, which the reader must follow** (fpp 3.4.0, unversioned internals):

- instances in `fpp-analysis.json` `.analysis.componentInstanceMap`, typed through the
  `DefComponent` AST node;
- connections in `.analysis.topologyMap[<id>].connectionMap`. A port number the FPP leaves implicit
  is `"None"` there, so the resolved number comes from `fromPortNumberMap` and `toPortNumberMap`.
  Connections arrive in no stable order, so member order is a sort by port number;
- constants in `.analysis.valueMap`, each held twice; use the definition node's id;
- annotations only in `fpp-ast.json`, one string per `@` line, pre and post;
- both topologies sit in `topologyMap`, so the reader selects the deployment by qualified name;
- the output embeds absolute paths, so it is not byte-reproducible across checkouts.

### `fprime-prm-write` and stock PrmDb: PASS (commit `9eccec3`, `spikes/fprime/`)

The JSON form, keyed by the dictionary's qualified instance name:

```json
{ "Spike.nav": { "mu": 3.986004418e14,
                 "dcm_PB": [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]] } }
```

```
$ fprime-prm-write dat prm/nav_case.json -d SpikeTopologyDictionary.json
$ python spike_check.py b prm/nav_case.dat
PrmFileLoadComplete : Parameter file load completed. Database: ACTIVE, Records: 2 (2 added and 0 updated).
nav.mu 398600441800000.0 valid
nav.dcm_PB [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]] valid
CHECK B PASS
```

With the file missing, PrmDb reports `PrmFileReadError` and both parameters stay invalid, so the
valid values came from the file. The tool fails with no `.dat` on an unqualified instance name, a
wrong parameter name, a wrong array length or a wrong type. `fprime-prm-decode` round-trips the
file byte for byte, but its default output path overwrites the input JSON, so it is always given
`-o`.

## Alternatives considered

- **The Python build speaking F´ packets, as in rev 1.** It keeps F´'s codec inside the Python
  build: a Python version of F´. Rejected for names at the ground and a ground station for the F´
  build.
- **`fpp to-layout` in place of the reader.** Named as the fallback, not taken. It is simpler to
  parse and resolved the import, but its instance names are unqualified and it carries no types,
  constants or annotations, so it could replace only the connections. It stays the fallback if the
  JSON shape churns.
- **`to-json` through F´'s wrapper.** It needs Java 25. Rejected for the native binary.
- **A Python writer and reader for F´'s binary parameter format.** It brings F´'s codec back into the
  Python build and duplicates F´'s own tool. Rejected for JSON plus `fprime-prm-write`.
- **The Python build taking `parameters(scenario)` directly, with a file only for F´.** The two
  builds would then not read one case record. Rejected.
- **A sandbox root of `/`.** It switches the protection off, so a ground-sent `prmDb.PRM_SAVE_FILE`
  could write anywhere. Rejected for the case's directory.
- **Parity over every command and every channel.** F´ generates commands the Python build lacks and
  gives no refusal reason, so the logs would never match. Rejected for a minimum spec.
- **Dictionaries for inputs, outputs, telemetry and parameters.** A misspelled key passes silently.
  Rejected for named tuples.
- **A hand-written passive dispatcher, or the stock one drained from outside.** The first
  reimplements F´'s responses and drifts; the second is impossible, since `CommandDispatcherImpl` is
  `final` and its dispatch protected. Rejected.
- **Commands and telemetry declared in Python, with FPP generated at port time; or a Python build
  reading the F´ build's dictionary.** The first moves the contract's source at port time; the second
  needs a compiler before an algorithm flies in Python. Rejected.
- **A role's entries as an FPP `interface`.** `fpp-check` rejects `telemetry` inside one. Rejected
  for included groups.
- **Each vector component as a scalar channel.** A quaternion over four channels is not one write.
  Rejected.
- **Telemetry sampled on the simulation's recording grid, or drained packed per tick.** The first
  lets the sim set the rate and lose writes; the second measured no gain. Rejected.

## Consequences

- The Python build holds no F´ codec. The F´ ground station is the only Python code that knows F´'s
  packets, and it is the part a real GDS replaces.
- Both builds answer in `Fw.CmdResponse` codes. Free-text reasons are an extra the Python build adds.
- A ported algorithm's F´ test asserts that its Python build's dictionary entries equal the F´
  build's, IDs aside, so a stale F´ build fails it.
- An `fprime-fpp` bump that moves the JSON shape fails issue 55's contract test on its Renovate PR,
  never mis-wires the Python build.
- The case's parameter path must stay under 240 characters, F´'s `FileNameStringSize`: a longer one
  asserts in PrmDb's sandbox, which raises in Python. Issue 60 parameters from a per-case file either
  keeps session paths short or raises the limit in the deployment's config.
- A new channel or command while prototyping is two edits: the `.fpp` line and the Python that writes
  or handles it.
- Generating a Python build's dictionary takes 0.1–0.3 s, once per process for each model.
- Reopened if an F´ release drops the cooperative task routine, a component needs to block, a
  consumer needs one vector component written apart, or the per-write log shows in a per-case
  profile.
