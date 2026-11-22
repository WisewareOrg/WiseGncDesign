"""The FPP files `fsw.codegen.fpp_model.read` is given: the contract's, and a WiseFsw deployment's.

A configuration's deployment topology is rendered by `render` from
`fsw/fprime/deployment/Fsw.fpp.in`: its `@CONFIGURATION@` token, and its `@SIMULATION@` token as the
role wiring generated from the roles the configuration's GNC sub-topology exposes
(`fsw.codegen.roles.taken`). The F´ build renders it with `python -m fsw.codegen.deployment`, so
the build and `fpp_files` read one rendering. The algorithms are every `.fpp` file in a directory
under `algorithms/`, and `algorithm_components` the components they define.
`configurations` names one configuration per GNC sub-topology, `fprime_configurations` those the
F´ build builds, and `gnc_instances` lists the GNC sub-topologies' instances.
`configuration_model` reads a configuration's contract and GNC sub-topology, `tick_period` its base
tick's period, and `bus_port` the LabBusDriver port its deployment wires to a CDH port.
"""

import functools
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from fsw.codegen.fpp_model import Instance, Model, read
from fsw.codegen.members import members
from fsw.codegen.roles import taken

__all__ = [
    "CLONE",
    "CONTRACT",
    "Contract",
    "REPOSITORY",
    "algorithm_components",
    "algorithm_files",
    "bus_port",
    "configuration_model",
    "configurations",
    "contract_files",
    "fpp_files",
    "fprime_configurations",
    "framework_files",
    "gnc_instances",
    "main",
    "render",
    "tick_period",
]

REPOSITORY = Path(__file__).resolve().parents[2]
"""The repository's root."""

CLONE = REPOSITORY / "fsw" / "fprime" / "lib" / "fprime"
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
    "fsw/fprime/rio/LabBusDriver.fpp",
    "fsw/fprime/deployment/instances.fpp",
)
"""The repository's files of every deployment's model, its algorithms and GNC sub-topology aside."""

_GNC = REPOSITORY / "fsw" / "fpp" / "gnc"
"""The GNC sub-topologies, one `<configuration>.fpp` per configuration."""

_TEMPLATE = REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in"
"""The deployment topology's template, rendered per configuration."""


def framework_files() -> tuple[Path, ...]:
    """The F´ framework files the model imports, in the clone `just _sync` fetches.

    Returns:
        The files, absolute.
    """
    return tuple(CLONE / path for path in _FRAMEWORK)


def algorithm_files() -> tuple[Path, ...]:
    """Every algorithm's FPP files: each `algorithms/*/*.fpp`, with or without an F´ component.

    Returns:
        The files, absolute, sorted.
    """
    return tuple(sorted(REPOSITORY.glob("algorithms/*/*.fpp")))


class Contract(NamedTuple):
    """The parts of a contract that vary: its algorithms and its GNC sub-topologies.

    The F´ framework's files and the repository's own, the interfaces and the deployment's
    stand-ins, are the spine every contract shares.

    Attributes:
        algorithms: the algorithms' `.fpp` files.
        gnc: the directory of the GNC sub-topologies, one `<configuration>.fpp` per configuration.
    """

    algorithms: tuple[Path, ...]
    gnc: Path


CONTRACT = Contract(algorithm_files(), _GNC)
"""The repository's contract: every algorithm, and the GNC sub-topologies in `fsw/fpp/gnc/`."""


@functools.cache
def algorithm_components() -> frozenset[str]:
    """The components an algorithm's `.fpp` defines, read once per process.

    Returns:
        Their qualified names.
    """
    algorithms = set(algorithm_files())
    return frozenset(
        c.name for c in read(contract_files()).components.values() if c.file in algorithms
    )


def contract_files(*, contract: Contract = CONTRACT) -> tuple[Path, ...]:
    """The files of the model every configuration shares, its GNC sub-topology and deployment aside.

    Args:
        contract: the contract, the repository's by default.

    Returns:
        The files, absolute: the framework's, the repository's, then the contract's algorithms'.
    """
    return (
        *framework_files(),
        *(REPOSITORY / path for path in _PROJECT),
        *contract.algorithms,
    )


def render(configuration: str, directory: Path, *, contract: Contract = CONTRACT) -> Path:
    """Renders a configuration's deployment topology into `directory`, its role wiring generated.

    The template's `@SIMULATION@` line becomes, for the k-th sensor role the configuration takes,
    `labBusDriver.busOut[k] -> cdh.<role>In` and `cdh.<role>Out -> <configuration>.Gnc.<role>In`,
    and for the k-th actuator role `<configuration>.Gnc.<role>Out -> cdh.<role>In` and
    `cdh.<role>Out -> labBusDriver.busIn[k]`, in `Cdh.BusConverter`'s order. A topology whose text
    is unchanged is not rewritten, so the F´ build does not autocode and compile it again.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in the contract's
            directory of them, such as `ImuDeadReckoning`.
        directory: where the rendered `<configuration>Fsw.fpp` is written.
        contract: the contract, the repository's by default.

    Returns:
        The rendered topology's path.
    """
    gnc = f"{configuration}.Gnc"
    roles = taken(configuration_model(configuration, contract=contract), configuration)
    sensors = [role for role in roles if role.sensor]
    actuators = [role for role in roles if not role.sensor]
    wiring = [
        line
        for k, role in enumerate(sensors)
        for line in (
            f"labBusDriver.busOut[{k}] -> cdh.{role.input}",
            f"cdh.{role.output} -> {gnc}.{role.input}",
        )
    ] + [
        line
        for k, role in enumerate(actuators)
        for line in (
            f"{gnc}.{role.output} -> cdh.{role.input}",
            f"cdh.{role.output} -> labBusDriver.busIn[{k}]",
        )
    ]
    text = _TEMPLATE.read_text().replace("@CONFIGURATION@", configuration)
    text = text.replace("@SIMULATION@\n", "".join(f"      {line}\n" for line in wiring))
    topology = directory / f"{configuration}Fsw.fpp"
    if not topology.is_file() or topology.read_text() != text:
        topology.write_text(text)
    return topology


def fpp_files(
    configuration: str, directory: Path, *, contract: Contract = CONTRACT
) -> tuple[Path, ...]:
    """Renders a configuration's deployment topology into `directory`, and lists its model's files.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in the contract's
            directory of them, such as `ImuDeadReckoning`.
        directory: where `render` writes the deployment topology.
        contract: the contract, the repository's by default.

    Returns:
        The files, absolute: the framework's, the repository's, the contract's algorithms', the
        configuration's GNC sub-topology, then its rendered deployment topology.
    """
    return (
        *contract_files(contract=contract),
        contract.gnc / f"{configuration}.fpp",
        render(configuration, directory, contract=contract),
    )


def configurations(*, contract: Contract = CONTRACT) -> tuple[str, ...]:
    """Every configuration: the name of each GNC sub-topology in the contract's directory of them.

    Args:
        contract: the contract, the repository's by default, whose are `fsw/fpp/gnc/`'s.

    Returns:
        The names, sorted, such as `ImuDeadReckoning`.
    """
    return tuple(sorted(path.stem for path in contract.gnc.glob("*.fpp")))


def fprime_configurations(*, contract: Contract = CONTRACT) -> tuple[str, ...]:
    """The configurations the F´ build builds: those whose every member has an F´ component.

    A member's component has an F´ component when the `.fpp` defining it sits in a directory
    holding a `CMakeLists.txt`, as an algorithm with an F´ component does.

    Args:
        contract: the contract, the repository's by default.

    Returns:
        The names, sorted, a subset of `configurations`.
    """
    return tuple(
        configuration
        for configuration in configurations(contract=contract)
        if _fprime_built(configuration, contract)
    )


def _fprime_built(configuration: str, contract: Contract) -> bool:
    """Whether each member of a configuration has an F´ component.

    Args:
        configuration: the configuration.
        contract: the contract holding it.

    Returns:
        Whether the `.fpp` defining each member's component has a `CMakeLists.txt` beside it.
    """
    model = configuration_model(configuration, contract=contract)
    return all(
        (model.components[member.component].file.parent / "CMakeLists.txt").is_file()
        for group in members(model, configuration).values()
        for member in group
    )


@functools.cache
def gnc_instances() -> tuple[Instance, ...]:
    """Every instance the GNC sub-topologies in `fsw/fpp/gnc/` define, read once per process.

    The contract defines the deployment's own instances, so those are left out.

    Returns:
        The instances.
    """
    sub_topologies = [_GNC / f"{configuration}.fpp" for configuration in configurations()]
    contract = read(contract_files()).instances
    return tuple(
        instance
        for name, instance in read((*contract_files(), *sub_topologies)).instances.items()
        if name not in contract
    )


@functools.cache
def configuration_model(configuration: str, *, contract: Contract = CONTRACT) -> Model:
    """A configuration's model: the contract and its GNC sub-topology, read once per process.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in the contract's
            directory of them, such as `ImuDeadReckoning`.
        contract: the contract, the repository's by default.

    Returns:
        The model.
    """
    return read((*contract_files(contract=contract), contract.gnc / f"{configuration}.fpp"))


def tick_period(configuration: str, *, contract: Contract = CONTRACT) -> float:
    """A configuration's base tick's period: the constant `tickPeriod` of its GNC sub-topology.

    Args:
        configuration: the configuration, such as `ImuDeadReckoning`.
        contract: the contract, the repository's by default.

    Returns:
        s, the period.

    Raises:
        KeyError: the sub-topology declares no `tickPeriod`, naming it.
    """
    constant = f"{configuration}.tickPeriod"
    constants = configuration_model(configuration, contract=contract).constants
    if constant not in constants:
        raise KeyError(f"{constant} is not declared in {contract.gnc / configuration}.fpp")
    return float(constants[constant])


@functools.cache
def bus_port(configuration: str, port: str, *, contract: Contract = CONTRACT) -> int:
    """The LabBusDriver port a configuration's deployment wires to a CDH port, in either direction.

    The deployment's topology is rendered and read once per process, and the port is the index `i`
    of its one connection between LabBusDriver and `WiseFsw.cdh.<port>`: a sensor's
    `WiseFsw.labBusDriver.busOut[i] -> WiseFsw.cdh.<role>In`, or an actuator's
    `WiseFsw.cdh.<role>Out -> WiseFsw.labBusDriver.busIn[i]`.

    Args:
        configuration: the configuration, such as `ImuDeadReckoning`.
        port: the CDH port, such as `imuIn`.
        contract: the contract, the repository's by default.

    Returns:
        The index of LabBusDriver's `busOut` or `busIn`.

    Raises:
        ValueError: the topology wires LabBusDriver to the port other than once, naming the
            configuration, the port and the indices found.
    """
    with tempfile.TemporaryDirectory() as directory:
        model = read(fpp_files(configuration, Path(directory), contract=contract))
    driver, cdh = ("WiseFsw.labBusDriver", "busOut"), ("WiseFsw.cdh", port)
    found = [
        connection.from_index
        for connection in model.topologies[f"WiseFsw.{configuration}Fsw"]
        if (connection.from_instance, connection.from_port) == driver
        and (connection.to_instance, connection.to_port) == cdh
    ] + [
        connection.to_index
        for connection in model.topologies[f"WiseFsw.{configuration}Fsw"]
        if (connection.from_instance, connection.from_port) == cdh
        and (connection.to_instance, connection.to_port) == ("WiseFsw.labBusDriver", "busIn")
    ]
    if len(found) != 1:
        raise ValueError(
            f"{configuration}'s deployment wires cdh.{port} to LabBusDriver port(s) {found},"
            " not one"
        )
    return found[0]


def main(argv: Sequence[str]) -> None:
    """Renders the deployment of every configuration the F´ build builds, and names each.

    The configurations are those of the repository's contract and of the test mocks',
    `fsw.mock.MOCK`, that `fprime_configurations` selects. Each is rendered into
    `<directory>/<configuration>/`, and printed on a line of its own as `<configuration>`, a tab,
    and its GNC sub-topology's absolute path; nothing else is printed.

    Args:
        argv: the directory, alone.
    """
    from fsw.mock import MOCK

    [directory] = argv
    for contract in (CONTRACT, MOCK):
        for configuration in fprime_configurations(contract=contract):
            out = Path(directory) / configuration
            out.mkdir(parents=True, exist_ok=True)
            render(configuration, out, contract=contract)
            print(f"{configuration}\t{contract.gnc / f'{configuration}.fpp'}")


if __name__ == "__main__":
    main(sys.argv[1:])
