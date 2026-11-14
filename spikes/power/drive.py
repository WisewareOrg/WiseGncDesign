"""Power-cycle spike: fly leo500 cases through FprimeModule, extension fresh per case or shared.

usage: drive.py MODE CASES [--duration S] [--fidelity lo] [--out FILE]
MODE: shared  (today: one import, boot per case)
      fresh   (a copy of the .so per case, loaded from its own path)
CASES: comma list of case indices, or N for range(N)
"""
import argparse, gc, importlib.util, importlib.machinery, json, os, pickle, shutil, sys, tempfile, time, weakref
from pathlib import Path
import numpy as np

REPO = Path("/home/wise/code/WiseGncDesign")
sys.path.insert(0, str(REPO))
import gnc_cdh.fprime.module as fmodule
from gnc_cdh.fprime import FprimeModule, DICTIONARY
from harness.ground import Ground
from scenarios import leo as leo_defs
from wise_dynamics.basilisk.scenarios import SCENARIOS
from wise_dynamics.basilisk.vehicles import VEHICLES
import wise_dynamics.pytest_plugin as plug

SO = next((REPO / "cdh/gnc_cdh/fprime").glob("_wise_fsw*.so"))
_current = None
_n = 0
_tmp = Path(tempfile.mkdtemp(prefix="wise_fsw_copies_"))
import atexit; atexit.register(lambda: shutil.rmtree(_tmp, ignore_errors=True))


def rss_mb():
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6


def fresh_copy(k):
    """A new copy of the .so under its own directory, loaded from that path: a new dlopen handle."""
    global _n
    _n += 1
    d = _tmp / f"copy{_n}"
    d.mkdir()
    dst = d / SO.name
    shutil.copy2(SO, dst)
    # pybind11 3 caches a completed module by its spec name in process-wide internals, so a second
    # copy under the name `_wise_fsw` returns the first copy's module. A distinct dotted name keeps
    # the init symbol (the last component) and gives each copy its own cache entry.
    name = f"wise_fsw_copy{_n}._wise_fsw"
    loader = importlib.machinery.ExtensionFileLoader(name, str(dst))
    spec = importlib.util.spec_from_loader(name, loader, origin=str(dst))
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)   # PyInit runs: Os::init + setupTopology on this copy's statics
    # The copy stays on disk until the worker exits, as a precaution: glibc keys a handle on
    # (st_dev, st_ino) and a freed inode can be reused. unlink_test.py unlinks each copy after
    # load and saw no aliasing in 4 copies, so unlinking looks safe but is not relied on.
    return mod


def fly(k, mode, duration_s, fidelity):
    global _current
    if mode == "fresh":
        _current = fresh_copy(k)
    else:
        import gnc_cdh.fprime._wise_fsw as m
        _current = m
    fmodule.extension = lambda: _current   # FprimeModule looks `extension` up at call time
    streams = np.random.SeedSequence(0, spawn_key=(k,)).spawn(2)
    sc = SCENARIOS["leo500"](vehicle_type=VEHICLES["imu_spacecraft"])
    sc.fidelity = fidelity
    sc.disperse(np.random.default_rng(streams[0]), noise_seed=int(streams[1].generate_state(1)[0]))
    fsw = FprimeModule(sc.vehicle.readers()["imu"], mu=sc.mu_m3_s2["earth"],
                       dcm_PB=np.asarray(sc.vehicle.imu.dcm_PB))
    ref = weakref.ref(sc)
    ground = Ground(leo_defs.leo500, fsw, sc.vehicle.tracking(), lambda: ref().stop_ground(), period_s=None)
    ds = sc.run(fsw, fsw_fields={}, duration_s=duration_s, ground=ground)
    if fsw.failure or ground.failure:
        raise fsw.failure or ground.failure
    ground.ensure_returned()
    ds |= ground.telemetry_datasets()
    return {k2: (np.asarray(v), u) for k2, (v, u) in ds.items()}, json.dumps(ground.command_log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode"); ap.add_argument("cases")
    ap.add_argument("--duration", type=float, default=5700.0)
    ap.add_argument("--fidelity", default="lo")
    ap.add_argument("--out"); ap.add_argument("--no-gc", action="store_true")
    a = ap.parse_args()
    cases = [int(x) for x in a.cases.split(",") if x] if "," in a.cases else list(range(int(a.cases)))
    results, log = {}, []
    for pos, k in enumerate(cases):
        t0 = time.perf_counter()
        res = fly(k, a.mode, a.duration, a.fidelity)
        dt = time.perf_counter() - t0
        if a.out:
            results[pos] = res
        del res
        if not a.no_gc:
            gc.collect()
        log.append((k, dt, rss_mb()))
        print(f"case {k} {dt:.3f}s rss {log[-1][2]:.1f}MB", flush=True)
    if a.out:
        with open(a.out, "wb") as f:
            pickle.dump({"results": results, "log": log}, f)


main()
