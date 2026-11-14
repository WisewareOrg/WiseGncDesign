# Power cycle by a fresh copy of `_wise_fsw` per case

Machine: this host, Python 3.14.7, pybind11 3.1.0, extension built in the main tree (696 KB, no GNU_UNIQUE). Case = leo500, lo fidelity, 5700 s, imu_spacecraft, FprimeModule + the repo's `Ground` and `scenarios.leo.leo500`, flown through `drive.py` (replicates `harness.mission._scenario_test` minus the run file).

Run everything: `spikes/power/run_all.sh`; compare: `python compare.py`; `python summarize.py res/*100*.log`.

## Mechanism (drive.py `fresh_copy`)
    shutil.copy2(SO, copydir/SO.name)
    name = f"wise_fsw_copy{n}._wise_fsw"              # dotted, unique per copy
    loader = ExtensionFileLoader(name, path); spec = spec_from_loader(name, loader, origin=path)
    mod = module_from_spec(spec); loader.exec_module(mod)   # PyInit runs: Os::init + setupTopology
    gnc_cdh.fprime.module.extension = lambda: mod            # FprimeModule resolves it at call time

Finding that changes the claim: loading a second copy under the spec name `_wise_fsw` returns the FIRST copy's module object. pybind11 3.1 caches a completed module by `__spec__.name` in process-wide internals (`get_cached_module`/`cache_completed_module`, common.h), so a different file path alone is not enough. The dotted unique spec name keeps the init symbol (last component) and gives each copy its own cache entry. Without it every "fresh" copy is the shared one.
`isolation.py`: two copies, both booted, only A stepped: A drains 1 telemetry write, B 0.
Copies are kept on disk until exit as a precaution (glibc keys a handle on st_dev/st_ino). `unlink_test.py` unlinked each copy after load and saw no aliasing in 4 copies, so unlink is probably safe but was not relied on.

## (1) State does not leak: PASS
Case 3 flown (a) alone, (b) after case 7, (c) as 3,7,3 in one process (first and third position), (d) in today's shared-extension build alone. All pairs: command log equal and all 15 datasets (85149 rows, including tlm/nav.* writes with their time tags) bytewise equal. Check can fail: case 7 differs from case 3. (`compare.py`)

## (2) Per-case time: PASS (no measurable cost)
n=100 each, cases 0..99:
| | mean | median |
|---|---|---|
| today (shared, boot per case) | 0.288 s | 0.286 s |
| fresh copy per case | 0.282 s | 0.281 s |
(no-gc runs: shared 0.275, fresh 0.280.) Copy + dlopen + setupTopology is inside the noise of 0.28 s. Case 0 of each run included.

## (3) RSS per worker over 100 cases: growth is real, 0.73 MB/case
| | start | end | slope |
|---|---|---|---|
| fresh, gc.collect() after each case | 261 MB | 334 MB | 737 kB/case |
| fresh, no gc | 262 | 336 | 730 kB/case |
| shared, gc | 261 | 260 | -8 kB/case |
| shared, no gc | 262 | 265 | 18 kB/case |
Not a leak by Python: each copy maps its own text/data (~0.7 MB .so) plus its own topology heap; dlclose is never called so nothing is returned. A worker flying N cases carries ~0.73 N MB: 460 cases = ~340 MB per worker if one worker flew them all. Mitigation if wanted: recycle the worker every K cases (K=100 costs ~75 MB). The #49 growth (cases flown with a ground held in memory) did NOT appear in the shared runs here (slope ~0 with or without gc), because the driver drops each case's scenario/ground; it was not reproduced by this driver, so "known leak not counted" is moot rather than measured.
An earlier version of the driver retained every case's datasets in a dict and showed 1.8 MB/case: driver artefact, fixed.

## Where the case's parameter-file path enters once setup moves into `boot()`
`FprimeModule.__init__(imu, mu, dcm_PB, [prm_path])` stores it; `Reset` calls `self._fsw.boot(mu=..., dcm_PB=..., prm_path=...)` (module.py:~129). With a fresh copy per case, `boot` is that copy's first and only call and runs `setupTopology` + PrmDb load; nothing else changes. The harness side: `fsw = mission.fsw(sim_scenario)` (harness/mission.py `_scenario_test`) is where a per-case path would be chosen, since `fprime_dead_reckoner(scenario)` builds the FprimeModule. Where the copy is made is `extension()` (module.py:~25), the one entry point.

## Open questions
- Design call: dotted spec name is load-bearing; `extension()` must own copy+load, and its rebuilt-stamp check (module.py) should stat the source .so, not the copy.
- Worker recycling policy for the 0.73 MB/case growth (not a failure of the check at 100 cases).
- Real run files not written; the datasets compared are those `sim_run_file` writes.
