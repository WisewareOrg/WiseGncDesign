"""FPP's model read through the native `fpp to-json`: the real deployment's, and a toy's.

The contract test reads the WiseFsw deployment's FPP, so a `fprime-fpp` bump that moves the JSON
shape fails here. Needs the F´ framework clone `just _sync` fetches, not an F´ build.
"""

import json
import subprocess
from pathlib import Path

import pytest

from fsw.codegen.deployment import CLONE, fpp_files
from fsw.codegen.fpp_model import (
    _FPP,
    Argument,
    Array,
    Channel,
    Command,
    Connection,
    Enum,
    Instance,
    Member,
    Model,
    Parameter,
    Port,
    Struct,
    TopologyPort,
    parse,
    read,
)

_TOY_FRAMEWORK = (
    "Fw/Cmd/Cmd.fpp",
    "Fw/Prm/Prm.fpp",
    "Fw/Time/Time.fpp",
    "Fw/Tlm/Tlm.fpp",
    "Fw/Types/Types.fpp",
    "cmake/platform/unix/Platform/PlatformTypes.fpp",
    "default/config/ComCfg.fpp",
    "default/config/FpConfig.fpp",
    "default/config/FpConstants.fpp",
)
"""The F´ framework files, in the clone, that the toy model imports."""

GNC = """\
module Gnc {

  @ nav runs every tick
  constant navDivider = 1
  constant gain = 2.5
  constant label = "gnc"
  constant enabled = true

  @ One IMU reading
  struct Reading {
    rate: F64
    accel: [3] F64
    count: U32
    label: string size 8
  }

  enum Mode: U8 {
    idle = 0
    running = 3
  }

  array Vector3 = [3] F64

  type Seconds = F64

  port Sched(ctx: U32)

  @ Rate group driver stand-in
  passive component RateGroup {
    sync input port CycleIn: Sched
    output port RateGroupMemberOut: [3] Sched
  }

  @ A navigation component
  @ provides: SRS010 free text, with spaces
  passive component Nav {
    sync input port schedIn: Sched
    command recv port cmdIn
    command reg port cmdRegOut
    command resp port cmdResponseOut
    telemetry port tlmOut
    time get port timeCaller
    param get port prmGetOut
    param set port prmSetOut

    sync command setMode(mode: Mode, reading: Reading) opcode 0x20
    sync command reset(after: Seconds) opcode 0x10

    telemetry rate: F64
    telemetry mode: Mode
    telemetry armed: bool
    telemetry elapsed: Seconds

    param gain: F64 default 2.0
    param startMode: Mode default Mode.running
    param mounting: Vector3
    param count: U32 default 7
    param armed: bool default true
    param tag: string default "x"
  }

  passive component Ctrl {
    sync input port schedIn: Sched
  }

  passive component Log {
    sync input port schedIn: Sched
  }

  @ pre-annotation on instance nav
  instance nav: Nav base id 0x1000 \\
    @< post-annotation on instance nav
  instance ctrl: Ctrl base id 0x2000
  instance log: Log base id 0x3000
  instance rg: RateGroup base id 0x4000

  @ GNC sub-topology
  topology Gnc {
    instance nav
    instance ctrl
    instance log
    instance rg
    connections Rates {
      rg.RateGroupMemberOut[2] -> log.schedIn
      rg.RateGroupMemberOut[0] -> nav.schedIn
      rg.RateGroupMemberOut[1] -> ctrl.schedIn
    }
    port tickIn = rg.CycleIn
  }

}
"""

TOP = """\
module Top {

  passive component Driver {
    output port tickOut: Gnc.Sched
  }

  instance drv: Driver base id 0x100

  @ The deployment
  topology Deploy {
    import Gnc.Gnc
    instance drv
    connections Tick {
      drv.tickOut -> Gnc.rg.CycleIn
    }
  }

}
"""


def _toy_files(directory: Path, gnc: str = GNC) -> list[Path]:
    """The toy model's files, its two modules written into `directory`.

    Args:
        directory: where `Gnc.fpp` and `Top.fpp` are written.
        gnc: the GNC module.

    Returns:
        The framework files, then `Gnc.fpp` and `Top.fpp`.
    """
    (directory / "Gnc.fpp").write_text(gnc)
    (directory / "Top.fpp").write_text(TOP)
    return [
        *(CLONE / path for path in _TOY_FRAMEWORK),
        directory / "Gnc.fpp",
        directory / "Top.fpp",
    ]


@pytest.fixture(scope="module")
def toy(tmp_path_factory: pytest.TempPathFactory) -> Model:
    """The toy model, read once.

    Args:
        tmp_path_factory: where the toy's model is written.

    Returns:
        The model.
    """
    return read(_toy_files(tmp_path_factory.mktemp("toy")))


def test_the_deployment_reads_back_with_every_connection_its_topology_declares(tmp_path: Path):
    """The dead reckoner's deployment: its instances and every connection, patterns included, read.

    Args:
        tmp_path: where the deployment's topology is rendered.
    """
    model = read(fpp_files("ImuDeadReckoning", tmp_path))

    assert model.instances == {
        "WiseFsw.simTime": Instance("WiseFsw.simTime", "Sim.SimTime", 0x100),
        "WiseFsw.groundLink": Instance("WiseFsw.groundLink", "Sim.GroundLink", 0x200),
        "WiseFsw.simBridge": Instance("WiseFsw.simBridge", "Sim.SimBridge", 0x300),
        "WiseFsw.cmdDisp": Instance("WiseFsw.cmdDisp", "Svc.CommandDispatcher", 0x500),
        "WiseFsw.prmDb": Instance("WiseFsw.prmDb", "Svc.PrmDb", 0x600),
        "ImuDeadReckoning.rateGroupDriver": Instance(
            "ImuDeadReckoning.rateGroupDriver", "Svc.RateGroupDriver", 0x400
        ),
        "ImuDeadReckoning.nav": Instance("ImuDeadReckoning.nav", "Gnc.ImuDeadReckoner", 0x1000),
        "ImuDeadReckoning.navRateGroup": Instance(
            "ImuDeadReckoning.navRateGroup", "Svc.PassiveRateGroup", 0x1100
        ),
    }
    dead_reckoner, rate_group = "ImuDeadReckoning.nav", "ImuDeadReckoning.navRateGroup"
    driver = "ImuDeadReckoning.rateGroupDriver"
    assert model.topologies["WiseFsw.ImuDeadReckoningFsw"] == (
        Connection(dead_reckoner, "cmdRegOut", 0, "WiseFsw.cmdDisp", "compCmdReg", 0),
        Connection(dead_reckoner, "cmdResponseOut", 0, "WiseFsw.cmdDisp", "compCmdStat", 0),
        Connection(dead_reckoner, "prmGetOut", 0, "WiseFsw.prmDb", "getPrm", 0),
        Connection(dead_reckoner, "prmSetOut", 0, "WiseFsw.prmDb", "setPrm", 0),
        Connection(dead_reckoner, "timeCaller", 0, "WiseFsw.simTime", "timeGetPort", 0),
        Connection(dead_reckoner, "tlmOut", 0, "WiseFsw.groundLink", "tlmIn", 0),
        Connection(rate_group, "CmdReg", 0, "WiseFsw.cmdDisp", "compCmdReg", 1),
        Connection(rate_group, "CmdStatus", 0, "WiseFsw.cmdDisp", "compCmdStat", 0),
        Connection(rate_group, "RateGroupMemberOut", 0, dead_reckoner, "schedIn", 0),
        Connection(rate_group, "Time", 0, "WiseFsw.simTime", "timeGetPort", 0),
        Connection(rate_group, "Tlm", 0, "WiseFsw.groundLink", "tlmIn", 0),
        Connection(driver, "CycleOut", 0, rate_group, "CycleIn", 0),
        Connection("WiseFsw.cmdDisp", "CmdReg", 0, "WiseFsw.cmdDisp", "compCmdReg", 2),
        Connection("WiseFsw.cmdDisp", "CmdStatus", 0, "WiseFsw.cmdDisp", "compCmdStat", 0),
        Connection("WiseFsw.cmdDisp", "Time", 0, "WiseFsw.simTime", "timeGetPort", 0),
        Connection("WiseFsw.cmdDisp", "Tlm", 0, "WiseFsw.groundLink", "tlmIn", 0),
        Connection("WiseFsw.cmdDisp", "compCmdSend", 0, dead_reckoner, "cmdIn", 0),
        Connection("WiseFsw.cmdDisp", "compCmdSend", 1, rate_group, "CmdDisp", 0),
        Connection("WiseFsw.cmdDisp", "compCmdSend", 2, "WiseFsw.cmdDisp", "CmdDisp", 0),
        Connection("WiseFsw.cmdDisp", "compCmdSend", 3, "WiseFsw.prmDb", "CmdDisp", 0),
        Connection("WiseFsw.cmdDisp", "seqCmdStatus", 0, "WiseFsw.groundLink", "cmdResponseIn", 0),
        Connection("WiseFsw.groundLink", "cmdOut", 0, "WiseFsw.cmdDisp", "seqCmdBuff", 0),
        Connection("WiseFsw.prmDb", "CmdReg", 0, "WiseFsw.cmdDisp", "compCmdReg", 3),
        Connection("WiseFsw.prmDb", "CmdStatus", 0, "WiseFsw.cmdDisp", "compCmdStat", 0),
        Connection("WiseFsw.prmDb", "Time", 0, "WiseFsw.simTime", "timeGetPort", 0),
        Connection("WiseFsw.simBridge", "imuOut", 0, dead_reckoner, "imuIn", 0),
        Connection("WiseFsw.simTime", "CycleOut", 0, driver, "CycleIn", 0),
    )
    assert model.constants["ImuDeadReckoning.navDivider"] == 1
    nav = model.components["Gnc.ImuDeadReckoner"]
    assert nav.commands == (
        Command(
            "initNavState",
            (
                Argument("epoch", "F64"),
                Argument("attitude", "Gnc.Quaternion"),
                Argument("position", "Gnc.Vector3"),
                Argument("velocity", "Gnc.Vector3"),
            ),
        ),
    )
    assert nav.channels == (
        Channel("navState", "Gnc.NavState"),
        Channel("bodyEciPos", "Gnc.Vector3"),
        Channel("bodyEciVel", "Gnc.Vector3"),
        Channel("bodyEciAttitude", "Gnc.Quaternion"),
    )
    assert model.types["Gnc.Matrix3"] == Array("Gnc.Matrix3", 3, "Gnc.Vector3")
    assert model.annotations["WiseFsw.ImuDeadReckoningFsw"] == (
        "The flight software run inside the simulation: the ImuDeadReckoning configuration's GNC,"
        " fed and",
        "ticked by the simulation, commanded and read by the ground",
    )


def test_an_imported_sub_topology_s_connections_are_the_deployment_s_in_port_order(toy: Model):
    """The deployment holds the imported group's connections, ordered by their from-numbers.

    Args:
        toy: the toy model.
    """
    assert toy.topologies["Top.Deploy"] == (
        Connection("Gnc.rg", "RateGroupMemberOut", 0, "Gnc.nav", "schedIn", 0),
        Connection("Gnc.rg", "RateGroupMemberOut", 1, "Gnc.ctrl", "schedIn", 0),
        Connection("Gnc.rg", "RateGroupMemberOut", 2, "Gnc.log", "schedIn", 0),
        Connection("Top.drv", "tickOut", 0, "Gnc.rg", "CycleIn", 0),
    )
    assert toy.topologies["Gnc.Gnc"] == toy.topologies["Top.Deploy"][:3]
    assert toy.instances["Gnc.rg"] == Instance("Gnc.rg", "Gnc.RateGroup", 0x4000)
    assert toy.instances["Top.drv"] == Instance("Top.drv", "Top.Driver", 0x100)


def test_a_topology_s_ports_are_read_as_the_instance_port_each_exposes(tmp_path: Path):
    """Keyed `<topology>.<port>`: the toy's, and the dead reckoner's GNC sub-topology's.

    Args:
        tmp_path: where the toy's model and the deployment's topology are written.
    """
    toy = read(_toy_files(tmp_path))
    model = read(fpp_files("ImuDeadReckoning", tmp_path))

    assert toy.ports == {"Gnc.Gnc.tickIn": TopologyPort("Gnc.rg", "CycleIn")}
    assert model.ports == {
        "ImuDeadReckoning.Gnc.tickIn": TopologyPort("ImuDeadReckoning.rateGroupDriver", "CycleIn"),
        "ImuDeadReckoning.Gnc.imuIn": TopologyPort("ImuDeadReckoning.nav", "imuIn"),
    }


def test_numeric_constants_are_read_by_qualified_name_and_others_are_not(toy: Model):
    """Integer and float constants are read, the framework's too; strings and bools are not.

    Args:
        toy: the toy model.
    """
    assert toy.constants["Gnc.navDivider"] == 1
    assert isinstance(toy.constants["Gnc.navDivider"], int)
    assert toy.constants["Gnc.gain"] == 2.5
    assert "Gnc.label" not in toy.constants
    assert "Gnc.enabled" not in toy.constants
    assert isinstance(toy.constants["FW_COM_BUFFER_MAX_SIZE"], int)


def test_annotations_are_read_pre_lines_then_post_lines(toy: Model):
    """A definition's `@` lines, then its `@<` lines; one with none has an empty tuple.

    Args:
        toy: the toy model.
    """
    assert toy.annotations["Gnc.nav"] == (
        "pre-annotation on instance nav",
        "post-annotation on instance nav",
    )
    assert toy.annotations["Gnc.Nav"] == (
        "A navigation component",
        "provides: SRS010 free text, with spaces",
    )
    assert toy.annotations["Gnc.navDivider"] == ("nav runs every tick",)
    assert toy.annotations["Gnc.Reading"] == ("One IMU reading",)
    assert toy.annotations["Gnc.Gnc"] == ("GNC sub-topology",)
    assert toy.annotations["Top.Deploy"] == ("The deployment",)
    assert toy.annotations["Gnc.ctrl"] == ()


def test_types_are_read_with_struct_members_in_declaration_order(toy: Model):
    """Structs keep FPP's member order; enums carry their constants and arrays their size.

    Args:
        toy: the toy model.
    """
    assert toy.types["Gnc.Reading"] == Struct(
        "Gnc.Reading",
        (
            Member("rate", "F64", None),
            Member("accel", "F64", 3),
            Member("count", "U32", None),
            Member("label", "string", None),
        ),
    )
    assert toy.types["Gnc.Mode"] == Enum("Gnc.Mode", "U8", {"idle": 0, "running": 3})
    assert toy.types["Gnc.Vector3"] == Array("Gnc.Vector3", 3, "F64")
    assert toy.types["Fw.CmdResponse"] == Enum(
        "Fw.CmdResponse",
        "U8",
        {
            "OK": 0,
            "INVALID_OPCODE": 1,
            "VALIDATION_ERROR": 2,
            "FORMAT_ERROR": 3,
            "EXECUTION_ERROR": 4,
            "BUSY": 5,
            "CLEARED": 6,
            "DISPATCHED_UNTRACKED": 7,
        },
    )
    assert "Gnc.Seconds" not in toy.types


def test_a_component_s_commands_channels_and_parameters_are_read(toy: Model):
    """Declared commands, channels and parameters, with defaults; F´'s PRM commands are not.

    Args:
        toy: the toy model.
    """
    nav = toy.components["Gnc.Nav"]

    assert nav.name == "Gnc.Nav"
    assert nav.commands == (
        Command("setMode", (Argument("mode", "Gnc.Mode"), Argument("reading", "Gnc.Reading"))),
        Command("reset", (Argument("after", "F64"),)),
    )
    assert nav.channels == (
        Channel("rate", "F64"),
        Channel("mode", "Gnc.Mode"),
        Channel("armed", "bool"),
        Channel("elapsed", "F64"),
    )
    assert nav.parameters == (
        Parameter("gain", "F64", 2.0),
        Parameter("startMode", "Gnc.Mode", "running"),
        Parameter("mounting", "Gnc.Vector3", None),
        Parameter("count", "U32", 7),
        Parameter("armed", "bool", True),
        Parameter("tag", "string", "x"),
    )
    assert [type(p.default) for p in nav.parameters] == [float, str, type(None), int, bool, str]


def test_a_component_s_general_output_ports_and_its_file_are_read(toy: Model):
    """Each output port that is not a special port, with its size and arguments, and the file.

    Args:
        toy: the toy model.
    """
    assert toy.components["Gnc.RateGroup"].outputs == (
        Port("RateGroupMemberOut", 3, (Argument("ctx", "U32"),)),
    )
    assert toy.components["Top.Driver"].outputs == (Port("tickOut", 1, (Argument("ctx", "U32"),)),)
    assert toy.components["Gnc.Nav"].outputs == ()
    assert toy.components["Gnc.Nav"].file.name == "Gnc.fpp"
    assert toy.components["Top.Driver"].file.name == "Top.fpp"
    assert toy.components["Gnc.Nav"].file.is_absolute()


def test_a_serial_output_port_reads_with_no_arguments(tmp_path: Path):
    """A `serial` output port, which has no port type, is an output with no arguments.

    Args:
        tmp_path: where the toy's model is written.
    """
    gnc = GNC.replace(
        "    command recv port cmdIn\n",
        "    output port anyOut: serial\n    command recv port cmdIn\n",
    )
    assert gnc != GNC

    nav = read(_toy_files(tmp_path, gnc)).components["Gnc.Nav"]

    assert nav.outputs == (Port("anyOut", 1, ()),)


def test_a_parameter_with_a_non_scalar_default_fails_naming_it(tmp_path: Path):
    """A default the reader does not convert raises, naming the parameter.

    Args:
        tmp_path: where the toy's model is written.
    """
    gnc = GNC.replace("param mounting: Vector3", "param mounting: Vector3 default [1.0, 0.0, 0.0]")

    with pytest.raises(ValueError, match="mounting"):
        read(_toy_files(tmp_path, gnc))


def test_a_model_fpp_rejects_fails_with_its_stderr(tmp_path: Path):
    """`to-json`'s refusal raises with what it printed.

    Args:
        tmp_path: where the toy's model is written.
    """
    gnc = GNC.replace("instance nav: Nav", "instance nav: Navigator")

    with pytest.raises(RuntimeError, match="Navigator"):
        read(_toy_files(tmp_path, gnc))


@pytest.mark.parametrize(
    "key", ["componentInstanceMap", "componentMap", "topologyMap", "typeMap", "valueMap"]
)
def test_a_renamed_analysis_key_fails_the_read(tmp_path: Path, key: str):
    """`parse` on output with a top-level analysis key it reads renamed raises, naming the key.

    Args:
        tmp_path: where the toy's model and `to-json`'s output are written.
        key: the analysis key renamed.
    """
    out = tmp_path / "out"
    model = tmp_path / "model"
    out.mkdir()
    model.mkdir()
    command = [str(_FPP), "to-json", "-d", str(out), *map(str, _toy_files(model))]
    subprocess.run(command, check=True, capture_output=True)
    analysis = out / "fpp-analysis.json"
    document = json.loads(analysis.read_text())
    document["analysis"][f"{key}Renamed"] = document["analysis"].pop(key)
    analysis.write_text(json.dumps(document))

    with pytest.raises(KeyError, match=key):
        parse(out)
