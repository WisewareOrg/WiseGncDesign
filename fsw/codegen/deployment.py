"""A WiseFsw deployment's FPP files, the list `fsw.codegen.fpp_model.read` is given for it.

A configuration's deployment topology is rendered from the template the F´ build renders, by the
same `@CONFIGURATION@` token.
"""

from pathlib import Path

__all__ = ["CLONE", "fpp_files"]

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
    "algorithms/imu_dead_reckoning/ImuDeadReckoner.fpp",
    "fsw/fpp/interfaces/Interfaces.fpp",
    "fsw/fprime/cdh/GroundLink.fpp",
    "fsw/fprime/platform/SimTime.fpp",
    "fsw/fprime/rio/SimBridge.fpp",
    "fsw/fprime/deployment/instances.fpp",
)
"""The repository's files of every deployment's model, its GNC sub-topology aside."""

_TEMPLATE = _REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in"
"""The deployment topology's template, rendered per configuration."""


def fpp_files(configuration: str, directory: Path) -> tuple[Path, ...]:
    """Every file of a configuration's deployment model, its topology rendered into `directory`.

    Args:
        configuration: the configuration, the name of its GNC sub-topology in `fsw/fpp/gnc/`, such
            as `ImuDeadReckoning`.
        directory: where the rendered `<configuration>Fsw.fpp` is written.

    Returns:
        The files, absolute: the framework's, the repository's, the configuration's GNC
        sub-topology, then its rendered deployment topology.
    """
    topology = directory / f"{configuration}Fsw.fpp"
    topology.write_text(_TEMPLATE.read_text().replace("@CONFIGURATION@", configuration))
    return (
        *(CLONE / path for path in _FRAMEWORK),
        *(_REPOSITORY / path for path in _PROJECT),
        _REPOSITORY / "fsw" / "fpp" / "gnc" / f"{configuration}.fpp",
        topology,
    )
