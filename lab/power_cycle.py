"""The one entry point to the deployment's extension: each call powers on a fresh copy of it.

A vehicle is power-cycled between flights; here each case flies its own copy of `_wise_fsw`, so no
component carries state from an earlier case. A copy is the source file copied into a temporary
directory of this process and loaded from there under the module name
`_power_cycle_<n>._wise_fsw`, `n` counted per process: pybind11 caches a module by that name, so a
copy under the source's own name would return the first copy loaded. The load uses Python's
default dlopen flags, which are `RTLD_LOCAL`, so each copy keeps its own statics. A copy never
enters `sys.modules` and its file is never unlinked while the process runs; the directory is
removed at exit.
"""

import atexit
import importlib.machinery
import importlib.util
import itertools
import os
import shutil
import tempfile
from pathlib import Path
from types import ModuleType

__all__ = ["power_cycle", "source"]

_SOURCE = "lab._wise_fsw"
"""The extension `just fsw` builds, by module name; it is located, never imported."""

_counter = itertools.count()
"""Numbers this process's copies."""

_directory: Path | None = None
"""The temporary directory holding this process's copies, made on the first power cycle."""

_loaded_stamp: tuple[int, int] | None = None
"""The source file's inode and modification time, in ns, when this process first checked it."""


def source() -> Path:
    """The extension's file, checked to be built and unchanged since this process first checked it.

    A process cannot drop a copy it loaded, so a source rebuilt after the first check is refused
    rather than mixed with copies of the old build. The source is stamped on the first call.

    Returns:
        The path of the extension `just fsw` built.

    Raises:
        ModuleNotFoundError: the extension is not built.
        RuntimeError: the extension file changed after this process first checked it.
    """
    global _loaded_stamp
    spec = importlib.util.find_spec(_SOURCE)
    if spec is None:
        raise ModuleNotFoundError("the F´ deployment is not built; run `just fsw`")
    path = Path(spec.origin)
    status = os.stat(path)
    stamp = (status.st_ino, status.st_mtime_ns)
    if _loaded_stamp is None:
        _loaded_stamp = stamp
    if stamp != _loaded_stamp:
        raise RuntimeError(
            f"{path} was rebuilt after this process loaded it;"
            " restart the kernel to fly the new build"
        )
    return path


def power_cycle() -> ModuleType:
    """A fresh copy of the extension, loaded and not yet booted: a new module on every call.

    The source is checked first, so an extension not built or rebuilt raises as `source` does.

    Returns:
        The copy's module, whose `boot` sets its topology up once.
    """
    global _directory
    path = source()
    if _directory is None:
        _directory = Path(tempfile.mkdtemp(prefix="wise_fsw_copies_"))
        atexit.register(shutil.rmtree, _directory, ignore_errors=True)
    n = next(_counter)
    copy = _directory / f"_power_cycle_{n}.{path.name}"
    shutil.copyfile(path, copy)
    name = f"_power_cycle_{n}.{path.name.split('.')[0]}"
    loader = importlib.machinery.ExtensionFileLoader(name, str(copy))
    spec = importlib.util.spec_from_loader(name, loader, origin=str(copy))
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
