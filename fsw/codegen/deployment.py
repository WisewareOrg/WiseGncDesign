"""The FPP files `fsw.codegen.fpp_model.read` is given: the contract's, and a WiseFsw deployment's.

A configuration's deployment topology is rendered from `fsw/fprime/deployment/Fsw.fpp.in`, the
template CMake's `configure_file` renders for the F´ build, by the same `@CONFIGURATION@` token. The
algorithms are those the F´ build takes: every directory under `algorithms/` with a
`CMakeLists.txt`. `gnc_instance` finds a component's instance in the GNC sub-topologies.
"""

import functools
from pathlib import Path

from fsw.codegen.fpp_model import Instance, read

__all__ = [
    "CLONE",
    "algorithm_files",
    "contract_files",
    "fpp_files",
    "framework_files",
    "gnc_instance",
]

_REPOSITORY = Path(__file__).resolve().parents[2]

CLONE = _REPOSITORY / "fsw" / "fprime" / "lib" / "fprime"
"""The F´ framework clone `just _sync` fetches."""

_FRAMEWORK = (
    "Drv/Interfaces/Tick.fpp",
    "Fpp/ToCpp.fpp",
    "Fw/Buffer/Buffer.fpp",
    "Fw/Cmd/Cmd.fpp",
    "Fw/Com/Com.fpp",
    "Fw/Dp/Dp.fpp",
    "Fw/Log/Log.fpp",
    "Fw/Prm/Prm.fpp",
    "Fw/Time/Time.fpp",
    "Fw/Tlm/Tlm.fpp",
    "Fw/Types/Types.fpp",
    "Os/Types.fpp",
    "Svc/Ccsds/Types/Types.fpp",
    "Svc/CmdDispatcher/CmdDispatcher.fpp",
    "Svc/Cycle/Cycle.fpp",
    "Svc/DpCompressProc/Types/CompressionTypes.fpp",
    "Svc/Interfaces/Time.fpp",
    "Svc/PassiveRateGroup/PassiveRateGroup.fpp",
    "Svc/PrmDb/PrmDb.fpp",
    "Svc/Ping/Ping.fpp",
    "Svc/RateGroupDriver/RateGroupDriver.fpp",
    "Svc/Sched/Sched.fpp",
    "cmake/platform/unix/Platform/PlatformTypes.fpp",
    "default/config/AcConstants.fpp",
    "default/config/ComCfg.fpp",
    "default/config/DpCfg.fpp",
    "default/config/FpConfig.fpp",
    "default/config/FpConstants.fpp",
    "default/config/FpySequencerCfg.fpp",
    "default/config/WasmSequencerCfg.fpp",
)
"""The F´ framework files the deployment's model imports, in the clone `just _sync` fetches."""

_PROJECT = (
    "fsw/fpp/interfaces/Bus.fpp",
    "fsw/fpp/interfaces/Interfaces.fpp",
    "fsw/fprime/cdh/GroundLink.fpp",
    "fsw/fprime/platform/SimTime.fpp",
    "fsw/fprime/rio/SimBridge.fpp",
    "fsw/fprime/deployment/instances.fpp",
)
"""The repository's files of every deployment's model, its algorithms and GNC sub-topology aside."""

_TEMPLATE = _REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in"
"""The deployment topology's template, rendered per configuration."""


def framework_files() -> tuple[Path, ...]:
    """The F´ framework files the model imports, in the clone `just _sync` fetches.

    Returns:
        The files, absolute.
    """
    return tuple(CLONE / path for path in _FRAMEWORK)


def algorithm_files() -> tuple[Path, ...]:
    """Every algorithm's FPP files: the `.fpp` files beside each `algorithms/*/CMakeLists.txt`.

    Returns:
        The files, absolute, sorted.
    """
    algorithms = sorted(_REPOSITORY.glob("algorithms/*/CMakeLists.txt"))
    return tuple(fpp for build in algorithms for fpp in sorted(build.parent.glob("*.fpp")))


def contract_files() -> tuple[Path, ...]:
    """The files of the model every configuration shares, its GNC sub-topology and deployment aside.

    Returns:
        The files, absolute: the framework's, the repository's, then every algorithm's.
    """
    return (
        *framework_files(),
        *(_REPOSITORY / path for path in _PROJECT),
        *algorithm_files(),
    )


def fpp_files(configuration: str, directory: Path) -> tuple[Path, ...]:
    """Renders a configuration's deployment topology into `directory`, and lists its model's files.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`, such
            as `ImuDeadReckoning`.
        directory: where the rendered `<configuration>Fsw.fpp` is written.

    Returns:
        The files, absolute: the framework's, the repository's, every algorithm's, the
        configuration's GNC sub-topology, then its rendered deployment topology.
    """
    topology = directory / f"{configuration}Fsw.fpp"
    topology.write_text(_TEMPLATE.read_text().replace("@CONFIGURATION@", configuration))
    return (
        *contract_files(),
        _REPOSITORY / "fsw" / "fpp" / "gnc" / f"{configuration}.fpp",
        topology,
    )


@functools.cache
def _gnc_instances() -> tuple[Instance, ...]:
    """Every instance the GNC sub-topologies in `fsw/fpp/gnc/` define, read once per process.

    The contract defines the deployment's own instances, so those are left out.

    Returns:
        The instances.
    """
    sub_topologies = sorted((_REPOSITORY / "fsw" / "fpp" / "gnc").glob("*.fpp"))
    contract = read(contract_files()).instances
    return tuple(
        instance
        for name, instance in read((*contract_files(), *sub_topologies)).instances.items()
        if name not in contract
    )


def gnc_instance(component: str) -> Instance:
    """The one instance of a component in the GNC sub-topologies.

    Args:
        component: the component's qualified FPP name, such as `Gnc.ImuDeadReckoner`.

    Returns:
        The instance, its qualified name such as `ImuDeadReckoning.nav`.

    Raises:
        ValueError: the component is instanced other than once, naming its instances.
    """
    found = [i for i in _gnc_instances() if i.component == component]
    if len(found) != 1:
        names = [i.name for i in found]
        raise ValueError(f"{component} is instanced {len(found)} times in fsw/fpp/gnc: {names}")
    return found[0]
