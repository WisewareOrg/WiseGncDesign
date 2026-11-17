"""The one entry point to each configuration's extension: each call powers on a fresh copy of it.

Each configuration's deployment is its own extension, `_wise_fsw_<configuration>`, with its
dictionary beside it. A vehicle is power-cycled between flights; here each case flies its own copy
of the extension, so no component carries state from an earlier case. A copy is the source file
copied into a temporary directory of this process and loaded from there under the module name
`_power_cycle_<n>._wise_fsw_<configuration>`, `n` counted per process: pybind11 caches a module
by that name, so a copy under the source's own name would return the first copy loaded. The load
uses Python's default dlopen flags, which are `RTLD_LOCAL`, so each copy keeps its own statics. A
copy never enters `sys.modules` and its file is never unlinked while the process runs; the
directory is removed at exit.
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

__all__ = ["built", "dictionary_path", "power_cycle", "source"]

_LAB = Path(__file__).parent
"""The directory `just fsw` builds each configuration's extension and dictionary into."""

_counter = itertools.count()
"""Numbers this process's copies."""

_directory: Path | None = None
"""The temporary directory holding this process's copies, made on the first power cycle."""

_loaded_stamps: dict[str, tuple[int, int]] = {}
"""Each configuration's source file's inode and modification time, in ns, when this process first
checked it."""


def dictionary_path(configuration: str) -> Path:
    """The dictionary F´ generated for a configuration's deployment, copied here by `just fsw`.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`.

    Returns:
        Its path, `lab/<configuration>FswTopologyDictionary.json`, built or not.
    """
    return _LAB / f"{configuration}FswTopologyDictionary.json"


def _extension(configuration: str) -> str:
    """A configuration's extension's module name.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`.

    Returns:
        `lab._wise_fsw_<configuration>`.
    """
    return f"lab._wise_fsw_{configuration}"


def built(configuration: str) -> bool:
    """Whether `just fsw` has built a configuration's extension.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`.

    Returns:
        True when its extension can be found.
    """
    return importlib.util.find_spec(_extension(configuration)) is not None


def source(configuration: str) -> Path:
    """A configuration's extension file, checked to be built and unchanged since first checked.

    A process cannot drop a copy it loaded, so a source rebuilt after this process first checked it
    is refused rather than mixed with copies of the old build. Each configuration's source is
    stamped on its first call.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`.

    Returns:
        The path of the configuration's extension `just fsw` built.

    Raises:
        ModuleNotFoundError: the extension is not built.
        RuntimeError: the extension file changed after this process first checked it.
    """
    spec = importlib.util.find_spec(_extension(configuration))
    if spec is None:
        raise ModuleNotFoundError(
            f"the F´ deployment of {configuration} is not built; run `just fsw`"
        )
    path = Path(spec.origin)
    status = os.stat(path)
    stamp = (status.st_ino, status.st_mtime_ns)
    if _loaded_stamps.setdefault(configuration, stamp) != stamp:
        raise RuntimeError(
            f"{path} was rebuilt after this process loaded it;"
            " restart the kernel to fly the new build"
        )
    return path


def power_cycle(configuration: str) -> ModuleType:
    """A fresh copy of a configuration's extension, loaded and not booted: a new module per call.

    The source is checked first, so an extension not built or rebuilt raises as `source` does.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`.

    Returns:
        The copy's module, whose `boot` sets its topology up once.
    """
    global _directory
    path = source(configuration)
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
