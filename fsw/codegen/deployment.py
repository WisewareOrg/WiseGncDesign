"""The FPP files `fsw.codegen.fpp_model.read` is given: the contract's, and a WiseFsw deployment's.

A configuration's deployment topology is rendered from `fsw/fprime/deployment/Fsw.fpp.in`, the
template CMake's `configure_file` renders for the F´ build, by the same `@CONFIGURATION@` token. The
algorithms are those the F´ build takes: every directory under `algorithms/` with a
`CMakeLists.txt`. `gnc_instances` lists the GNC sub-topologies' instances, and `gnc_instance`
finds a component's one instance among them. `configuration_model` reads a configuration's contract
and GNC sub-topology, `tick_period` its base tick's period, and `bus_port` the SimHub port its
deployment wires to a CDH input port.
"""

import functools
import tempfile
from pathlib import Path

from fsw.codegen.fpp_model import Instance, Model, read

__all__ = [
    "CLONE",
    "algorithm_files",
    "bus_port",
    "configuration_model",
    "contract_files",
    "fpp_files",
    "framework_files",
    "gnc_instance",
    "gnc_instances",
    "tick_period",
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
    "fsw/fpp/interfaces/Cdh.fpp",
    "fsw/fpp/interfaces/Interfaces.fpp",
    "fsw/fprime/cdh/GroundLink.fpp",
    "fsw/fprime/platform/SimTime.fpp",
    "fsw/fprime/rio/SimHub.fpp",
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
def gnc_instances() -> tuple[Instance, ...]:
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
    found = [i for i in gnc_instances() if i.component == component]
    if len(found) != 1:
        names = [i.name for i in found]
        raise ValueError(f"{component} is instanced {len(found)} times in fsw/fpp/gnc: {names}")
    return found[0]


@functools.cache
def configuration_model(configuration: str) -> Model:
    """A configuration's model: the contract and its GNC sub-topology, read once per process.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`, such
            as `ImuDeadReckoning`.

    Returns:
        The model.
    """
    return read((*contract_files(), _REPOSITORY / "fsw" / "fpp" / "gnc" / f"{configuration}.fpp"))


def tick_period(configuration: str) -> float:
    """A configuration's base tick's period: the constant `tickPeriod` of its GNC sub-topology.

    Args:
        configuration: the configuration, such as `ImuDeadReckoning`.

    Returns:
        s, the period.

    Raises:
        KeyError: the sub-topology declares no `tickPeriod`, naming it.
    """
    constant = f"{configuration}.tickPeriod"
    constants = configuration_model(configuration).constants
    if constant not in constants:
        raise KeyError(f"{constant} is not declared in fsw/fpp/gnc/{configuration}.fpp")
    return float(constants[constant])


@functools.cache
def bus_port(configuration: str, port: str) -> int:
    """The SimHub port wired to a CDH input port in a configuration's deployment, once per process.

    The deployment's topology is rendered and read, and the port is the index `i` of its one
    connection `WiseFsw.simHub.busOut[i] -> WiseFsw.cdh.<port>`.

    Args:
        configuration: the configuration, such as `ImuDeadReckoning`.
        port: the CDH input port, such as `imuIn`.

    Returns:
        The index of SimHub's `busOut`.

    Raises:
        ValueError: the topology wires SimHub to the port other than once, naming the
            configuration, the port and the indices found.
    """
    with tempfile.TemporaryDirectory() as directory:
        model = read(fpp_files(configuration, Path(directory)))
    found = [
        connection.from_index
        for connection in model.topologies[f"WiseFsw.{configuration}Fsw"]
        if (connection.from_instance, connection.from_port) == ("WiseFsw.simHub", "busOut")
        and (connection.to_instance, connection.to_port) == ("WiseFsw.cdh", port)
    ]
    if len(found) != 1:
        raise ValueError(
            f"{configuration}'s deployment wires cdh.{port} to SimHub port(s) {found}, not one"
        )
    return found[0]
