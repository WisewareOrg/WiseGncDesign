# 0002 — Fly missions from notebooks against a requirements tree

**Status:** accepted
**Decided:** 2026-11-13 (issue 39 scenarios command the flight software)
**Rev:** 2

## Revisions

- **rev 2** — 2026-11-13 — a TST definition is a ground procedure that commands the flight
  software (issue 39 scenarios command the flight software).
- **rev 1** — 2026-11-11 — first written (issue 29 missions).

## Context

ADR 0001 rev 2 judges a Monte Carlo session with requirement analyzers, and leaves open where the
requirements and their limits are stored and how a test is tied to a requirement. Three needs
follow.

- The requirements need a home that reviews them and notices when something they depend on changes.
- A flight is a hardware and software combination flown through a scenario, and the same flight
  software must be flown on more than one vehicle, so a Monte Carlo test cannot carry the whole
  combination in a tag.
- Work happens in notebooks. Defining a flight, flying it, judging it and plotting it belong in
  one place, and the same flight must also run unattended in CI.

## Decision

### The requirements tree

- **A Doorstop tree under `docs/requirements/`, checked by `check-reqs`.** Three documents, SYS,
  SRS and TST. Every item and link carries a review stamp, and the tree fails the check when a
  reviewed item changes unreviewed.
- **SYS is a capability, SRS is a rung of performance, TST is a scenario.** A SYS item is a
  capability tied to the components that provide it. An SRS item is one rung of a capability's
  ladder, with `x`, `p` and `c` as attributes of the item and its text stating the metric and window;
  any number of capabilities claim a rung, and a ladder is designed so that not every rung passes.
  A TST item is a scenario.
- **The requirement-to-scenario link is in the tree.** A TST links to the rungs it evaluates, and each
  scenario is judged as its own cell.
- **Duration and case count belong to the scenario.** A different duration or case count is a
  different TST. The TST references the code that says how it is flown, by file and `def` line;
  Doorstop does not drive the simulator.
- **A TST definition is its ground procedure.** The referenced `def` is an `async def` that the
  ground of
  [ADR 0004 rev 1](0004-carry-commands-and-telemetry-in-fprime-s-form-from-one-fpp-dictionary.md)
  runs against the flight software from t = 0: it waits on time or telemetry and sends commands,
  so a scenario that needs the flight software commanded, such as one initializing navigation from
  tracking, says so in the one place that says how it is flown. Its `sim_` marks are the rest. The
  procedure's return does not end the flight, whose duration stays the one stopping rule, and an
  exception in the procedure, such as a command refused or a wait timed out, crashes the case,
  which the verdict counts as a failure.
- **Reference hashes are on.** A TST records the hash of the file it references when reviewed, and
  `check-reqs` fails when that file changes, so changing how a scenario is flown re-flags its TST.
  Scenarios share one file, so editing one re-flags every TST that references it.
- **The tree's items, rung values and case counts are placeholders** for exercising the plumbing.

### Missions

- **A mission is a value in a notebook, outside the tree.** It holds a vehicle, an FSW builder and
  the scenarios to fly, by TST ID, and optionally a filter of the rungs to judge, by SRS ID.
  `mission_tests` turns missions into Monte Carlo tests when the notebook is collected.
- **The FSW builder claims its capabilities** with `@provides("SYS...")`. Adding an FSW touches no
  tree item.
- **The vehicle is a mission parameter**, flown through the simulator's `sim_vehicle` mark and its
  `VEHICLES` registry. One session may hold several vehicles.
- **A flight is a vehicle, an FSW and a scenario.** `mission_tests` makes a class per vehicle and a
  test per FSW and scenario, so each flight has a folder of its own in the session. Two missions
  flying the same flight are an error raised before anything flies.
- **The rungs a flight is judged on are worked out**: the rungs its scenario links to that sit under
  a capability its FSW claims. A mission's rung filter is optional; each rung it lists must be one
  of those, checked against the union of the mission's scenarios when the `Mission` is built, so a
  disagreement fails in the cell that defines it. A flight with no rung to judge is an error when
  the mission is built. One shared rule works out a flight's rungs, for missions and for the judge.
- **An algorithm notebook is a mission like any other**: the algorithm's derivation and
  implementation, then its mission. A notebook may define scenarios of its own for TST items to
  reference; a TST that points into a notebook is re-flagged for review on every edit to that
  notebook.
- **The same flight may be flown from two notebooks.** Each notebook stays self-contained, at the
  cost of flying the same cases twice; the two land in different folders.

### Judging

- **Judging is read in the notebook.** `judge()` returns the matrix, a row per rung and a column per
  flight, and prints why any rung failed or was not judged; `plots(<SRS ID>)` shows a rung's plots.
  `just judge` runs the same analyzers from a terminal. The analyzers are not collected by the
  suite's default run.
- **An analyzer judges one metric, for every rung whose tree reference names its file.** The test is
  parametrized over those rungs, one pytest item per rung. Its error math and its plot are in its
  own file, and the rung's limits come from its tree item.
- **The judge learns what a flight was from facts recorded when it flew.** Before its first case
  setup, the flight writes `flight.json` beside its runs: scenario, claimed capabilities and rung
  filter. The judge reads those with the tree at judge time and never executes a notebook. A change
  to the tree applies to existing runs; a change to an FSW's claims or to a mission's filter counts
  after a re-flight. A flight whose every case crashed is still judged, as all failures. The
  simulator records nothing about missions and tells a test where its runs live.
- **A rung's verdict is two checks.** Each run's number is compared with `x`, and a run that is over
  it, or crashed, is a failure. Then the failures are compared with the allowance `k` for the `n`
  runs found, which also says whether `n` shows `p` at `c` at all; if not, the cell is not judged.
  `n` is the runs found, not a planned count, so an interrupted campaign is judged on the cases that
  finished. A rung passes only when every flight judging it passes.
- **Judging clears the session's `report/` first**, so the matrix shows only what this judging
  produced. The report is a view of the runs, rebuilt every time.
- **A folder without `flight.json`, or whose test file is gone, is skipped and listed** in the
  report rather than judged.

### Capped runs and the suite

The simulator behaviour this repository relies on: a Monte Carlo test flies two cases unless
`--full-monte-carlo` is passed; capped runs go into a fixed scratch session, `monte_carlo/scratch/`,
whatever the session pointer says, so a capped run never replaces evidence; and a campaign of `N`
cases starting clears that test's cases numbered `N` and above, so the leftovers of an earlier,
larger campaign never mix in. A variable set only by notebook-run tests forces capped runs
everywhere, even with `--full-monte-carlo`, and the session name `scratch` is reserved.

- **The `%%monte_carlo` magic and `just fly` pass `--full-monte-carlo`.** Bare `pytest`, the VS Code
  test explorer, `just test` and CI do not, so none of them flies a full campaign by accident.
- **One suite.** Each notebook is run end to end in a kernel by the test file beside it, at two
  cases a flight, and notebooks are not collected as test modules, so nothing flies twice.
  `just test`, bare `pytest` and CI are the same run. The judge finds its session inside pytest, so
  capped runs are judged in `scratch`.

### Layout

- **Machinery apart from content.** `harness/`, a package at the repository root imported as
  `harness.<module>`, holds what knows no specific requirement, metric or scenario: the mission
  code, the judging fixtures as a pytest plugin, `judge()` and `plots()`, and the tree reader.
  Content stays where it is read: `analysis/` holds only the analyzers, `scenarios/` holds how each
  TST is flown, and `algorithms/`, `missions/` and `cdh/` hold the rest.
- **Tests sit beside the code they test**, with no central `tests/` folder. Same-named test files
  stay apart under `--import-mode=importlib`.
- **An algorithm is a package around its notebook.** The notebook keeps the derivation and the
  implementation readable together; the gross check and the tests live in the package.
- **`gnc_algorithms` is a workbook, not a library.** It is installed editable so notebooks and tests
  import it, and is never shipped on its own. Its notebooks import the harness and the analyzers on
  purpose, and the F´ flight software, which is C++, never imports it.

### From the simulator

The repository relies on the simulator providing a public function that finds the active session
outside pytest, and on each run file recording the calling repository's commit and whether its tree
was dirty. Run files carry no GNC attributes.

## Alternatives considered

- **A lighter tree without a TST tier.** The link from rung to scenario would then live in code,
  where nothing reviews it. Rejected.
- **SYS as a mission's wants, with requirements flowed down from it.** Rejected: a capability and the
  wants of one mission are different things, and rungs are shared across capabilities.
- **TST items owned by missions.** Rejected: a scenario is judged for every mission that flies it.
- **A procedure apart from the definition**, referenced from it by name or kept in a registry of
  procedures. It adds a name to keep in step and a second reference per TST, and the TST's hash
  would no longer cover how the scenario commands the flight software. Rejected for the definition
  being the procedure.
- **A failed procedure recorded in the run file and the case judged.** A case whose procedure
  failed did not fly the scenario its TST states, so judging it judges something else. Rejected for
  a crash.
- **The procedure's return ending the flight.** The flight's length would then depend on how the
  flight software answered. Rejected: the duration is the stopping rule.
- **`c` on the TST.** Rejected: confidence belongs to the demonstration a rung demands, so it
  belongs to the rung.
- **`scenario` and `runs` attributes on the TST.** Rejected: the TST references the code that flies
  the scenario, and a second statement of it can only disagree.
- **A mission inside the tree.** Rejected: what flies is a choice of the notebook, not a
  requirement.
- **A mission only as a fixture.** Rejected: a fixture runs too late to decide which tests exist.
- **Passing scenario definitions to a mission instead of IDs.** Rejected: the tree is the one place
  that names a scenario.
- **The mission listing the FSW's capabilities**, **deriving them from the rungs** or **a SYS item
  referencing a builder.** Rejected: the first restates what the builder knows, the second fails
  because rungs are shared, and the third makes the tree know which FSWs exist.
- **A mission name identifying a flight.** Rejected: the same flight under two names would fly
  twice into one folder.
- **Algorithm notebooks flying campaigns the tree never judges.** Rejected: a campaign nobody judges
  is not evidence.
- **A required rung list on the mission.** It must agree with the tree and with the FSW's claims and
  disagreed silently. Rejected, as was no list at all, which loses the allowlist.
- **Re-importing each notebook at judge time.** One broken notebook would break all judging, and old
  runs would be judged against current claims. Rejected.
- **The flight's facts in run files.** A flight whose every case crashed has no run file to judge
  from. Rejected.
- **Keeping old report cells marked stale.** Rejected: the report is a view of the runs, and a record
  is the as-run phase's concern.
- **Judging in the VS Code test explorer.** It judged whatever session was active. Rejected for
  reading verdicts in the notebook.
- **Capping only in recipes.** Bare `pytest` would still fly full campaigns. Rejected for capping by
  default.
- **Collecting notebooks as test modules beside running them in a kernel.** Every flight would fly
  twice. Rejected for one suite.
- **Splitting `analysis/` into a flying side and a judging side.** It filed the judge's machinery with
  its content. Rejected for machinery apart from content.
- **A nested `harness/gnc_harness/` folder.** Rejected for a package at the root.
- **A central `tests/` folder.** Rejected: pytest documents tests beside code, and NumPy, SciPy and
  pandas use that layout.
- **A mission notebook flying only what an algorithm notebook does not.** Rejected: each notebook
  shows its own complete picture.
- **Separating algorithm code from its notebook.** Rejected: it undoes the notebook that keeps
  derivation and implementation together. A cleaner split may come later, for its own reasons.

## Consequences

- A new FSW is judged by claiming its capabilities; a new vehicle is a field of a mission; a new
  scenario is a TST and the code it references.
- Editing how a scenario is flown re-flags its TST for review, its procedure included.
- A scenario's procedure names the commands it sends, so a flight software without them crashes
  every case of that scenario, and flies a sibling TST instead.
- Judging is repeatable and never simulates, and an old session is judged against the tree as it
  stands.
- A change to an FSW's claims or a mission's filter does not reach existing runs until the flight
  flies again.
- Folders are skipped and listed, not hidden, so a renamed notebook shows up in the report.
- Notebooks and their algorithm packages depend on the harness and the analyzers, so an algorithm
  cannot be lifted out of this repository unchanged.
