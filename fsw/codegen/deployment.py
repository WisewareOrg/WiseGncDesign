"""The WiseFsw deployment's FPP files, the one list `fsw.codegen.fpp_model.read` is given for it."""

from pathlib import Path

__all__ = ["CLONE", "FPP_FILES"]

_REPOSITORY = Path(__file__).resolve().parents[2]

CLONE = _REPOSITORY / "fsw" / "fprime" / "lib" / "fprime"
"""The F´ framework clone `just _sync` fetches."""

_FRAMEWORK = (
    "Drv/Interfaces/Tick.fpp",
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
    "fsw/fpp/gnc/ImuDeadReckoning.fpp",
    "fsw/fprime/cdh/GroundLink.fpp",
    "fsw/fprime/platform/SimTime.fpp",
    "fsw/fprime/rio/SimBridge.fpp",
    "fsw/fprime/configurations/imu_dead_reckoning/topology.fpp",
)
"""The repository's files of the deployment's model."""

FPP_FILES: tuple[Path, ...] = (
    *(CLONE / path for path in _FRAMEWORK),
    *(_REPOSITORY / path for path in _PROJECT),
)
"""Every file of the WiseFsw deployment's model, absolute: the framework's, then the project's."""
