"""FPP's model read through the native `fpp to-json`: the real deployment's, and a mock's.

The contract test reads the WiseFsw deployment's FPP, so a `fprime-fpp` bump that moves the JSON
shape fails here. Needs the F´ framework clone `just _sync` fetches, not an F´ build.
"""

import json
import subprocess
from pathlib import Path

import pytest

from fsw.codegen.deployment import algorithm_components, fpp_files, framework_files
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
from fsw.codegen.members import members
from fsw.codegen.roles import roles
from fsw.mock import edited

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

  array Matrix = [3] Vector3

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


def _mock_files(directory: Path, gnc: str = GNC) -> list[Path]:
    """The mock model's files, its two modules written into `directory`, with the framework's.

    Args:
        directory: where `Gnc.fpp` and `Top.fpp` are written.
        gnc: the GNC module.

    Returns:
        The framework files, then `Gnc.fpp` and `Top.fpp`.
    """
    (directory / "Gnc.fpp").write_text(gnc)
    (directory / "Top.fpp").write_text(TOP)
    return [
        *framework_files(),
        directory / "Gnc.fpp",
        directory / "Top.fpp",
    ]


@pytest.fixture(scope="module")
def mock(tmp_path_factory: pytest.TempPathFactory) -> Model:
    """The mock model, read once.

    Args:
        tmp_path_factory: where the mock's model is written.

    Returns:
        The model.
    """
    return read(_mock_files(tmp_path_factory.mktemp("mock")))


def test_the_deployment_reads_back_with_every_connection_its_topology_declares(
    configuration: str, tmp_path: Path
):
    """A configuration's deployment: every connection read, the pattern graphs' included.

    Every connection end is an instance of the model, of a component it defines. Each GNC member's
    connections show F´'s pattern graphs were read: a member with commands registers with the
    dispatcher and is sent commands by it, one with channels reaches the ground link and the clock,
    and one with parameters reads PrmDb. Each role the sub-topology takes comes from the CDH's
    output into a member, every algorithm instance is a member its rate groups run, and the
    sub-topology's tick comes in at its rate group driver.

    Args:
        configuration: the configuration.
        tmp_path: where the deployment's topology is rendered.
    """
    model = read(fpp_files(configuration, tmp_path))
    connections = model.topologies[f"WiseFsw.{configuration}Fsw"]

    assert connections
    for c in connections:
        assert c.from_instance in model.instances, c
        assert c.to_instance in model.instances, c
    for instance in model.instances.values():
        assert instance.component in model.components, instance.name
    flown = [member for group in members(model, configuration).values() for member in group]
    assert flown
    for member in flown:
        component = model.components[member.component]
        targets = {
            (c.to_instance, c.to_port) for c in connections if c.from_instance == member.name
        }
        sent = {(c.from_instance, c.from_port) for c in connections if c.to_instance == member.name}
        if component.commands:
            assert ("WiseFsw.cmdDisp", "compCmdReg") in targets, member.name
            assert ("WiseFsw.cmdDisp", "compCmdSend") in sent, member.name
        if component.channels:
            assert ("WiseFsw.groundLink", "tlmIn") in targets, member.name
            assert ("WiseFsw.simTime", "timeGetPort") in targets, member.name
        if component.parameters:
            assert ("WiseFsw.prmDb", "getPrm") in targets, member.name
    names = {member.name for member in flown}
    for role in roles(model):
        port = model.ports.get(f"{configuration}.Gnc.{role.input}")
        if port is None:
            continue
        cdh = ("WiseFsw.cdh", role.output, port.instance, port.port)
        ends = {(c.from_instance, c.from_port, c.to_instance, c.to_port) for c in connections}
        assert cdh in ends, role.role
        assert port.instance in names, role.role
    algorithms = {
        name
        for name, instance in model.instances.items()
        if name.startswith(f"{configuration}.") and instance.component in algorithm_components()
    }
    assert algorithms <= names
    tick = model.ports[f"{configuration}.Gnc.tickIn"]
    assert model.instances[tick.instance].component == "Svc.RateGroupDriver"
    assert tick.port == "CycleIn"


def test_an_imported_sub_topology_s_connections_are_the_deployment_s_in_port_order(mock: Model):
    """The deployment holds the imported group's connections, ordered by their from-numbers.

    Args:
        mock: the mock model.
    """
    assert mock.topologies["Top.Deploy"] == (
        Connection("Gnc.rg", "RateGroupMemberOut", 0, "Gnc.nav", "schedIn", 0),
        Connection("Gnc.rg", "RateGroupMemberOut", 1, "Gnc.ctrl", "schedIn", 0),
        Connection("Gnc.rg", "RateGroupMemberOut", 2, "Gnc.log", "schedIn", 0),
        Connection("Top.drv", "tickOut", 0, "Gnc.rg", "CycleIn", 0),
    )
    assert mock.topologies["Gnc.Gnc"] == mock.topologies["Top.Deploy"][:3]
    assert mock.instances["Gnc.rg"] == Instance("Gnc.rg", "Gnc.RateGroup", 0x4000)
    assert mock.instances["Top.drv"] == Instance("Top.drv", "Top.Driver", 0x100)


def test_a_topology_s_ports_are_read_as_the_instance_port_each_exposes(mock: Model):
    """Keyed `<topology>.<port>`.

    Args:
        mock: the mock model.
    """
    assert mock.ports == {"Gnc.Gnc.tickIn": TopologyPort("Gnc.rg", "CycleIn")}


def test_numeric_constants_are_read_by_qualified_name_and_others_are_not(mock: Model):
    """Integer and float constants are read, the framework's too; strings and bools are not.

    Args:
        mock: the mock model.
    """
    assert mock.constants["Gnc.navDivider"] == 1
    assert isinstance(mock.constants["Gnc.navDivider"], int)
    assert mock.constants["Gnc.gain"] == 2.5
    assert "Gnc.label" not in mock.constants
    assert "Gnc.enabled" not in mock.constants
    assert isinstance(mock.constants["FW_COM_BUFFER_MAX_SIZE"], int)


def test_annotations_are_read_pre_lines_then_post_lines(mock: Model):
    """A definition's `@` lines, then its `@<` lines; one with none has an empty tuple.

    Args:
        mock: the mock model.
    """
    assert mock.annotations["Gnc.nav"] == (
        "pre-annotation on instance nav",
        "post-annotation on instance nav",
    )
    assert mock.annotations["Gnc.Nav"] == (
        "A navigation component",
        "provides: SRS010 free text, with spaces",
    )
    assert mock.annotations["Gnc.navDivider"] == ("nav runs every tick",)
    assert mock.annotations["Gnc.Reading"] == ("One IMU reading",)
    assert mock.annotations["Gnc.Gnc"] == ("GNC sub-topology",)
    assert mock.annotations["Top.Deploy"] == ("The deployment",)
    assert mock.annotations["Gnc.ctrl"] == ()


def test_types_are_read_with_struct_members_in_declaration_order(mock: Model):
    """Structs keep FPP's member order; enums carry their constants, arrays their size and element.

    Args:
        mock: the mock model.
    """
    assert mock.types["Gnc.Reading"] == Struct(
        "Gnc.Reading",
        (
            Member("rate", "F64", None),
            Member("accel", "F64", 3),
            Member("count", "U32", None),
            Member("label", "string", None),
        ),
    )
    assert mock.types["Gnc.Mode"] == Enum("Gnc.Mode", "U8", {"idle": 0, "running": 3})
    assert mock.types["Gnc.Vector3"] == Array("Gnc.Vector3", 3, "F64")
    assert mock.types["Gnc.Matrix"] == Array("Gnc.Matrix", 3, "Gnc.Vector3")
    assert mock.types["Fw.CmdResponse"] == Enum(
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
    assert "Gnc.Seconds" not in mock.types


def test_a_component_s_commands_channels_and_parameters_are_read(mock: Model):
    """Declared commands, channels and parameters, with defaults; F´'s PRM commands are not.

    Args:
        mock: the mock model.
    """
    nav = mock.components["Gnc.Nav"]

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


def test_a_component_s_general_ports_and_its_file_are_read(mock: Model):
    """Each general port, in FPP's order with its size and arguments, and the component's file.

    A general port is one that is not a special port.

    Args:
        mock: the mock model.
    """
    assert mock.components["Gnc.RateGroup"].outputs == (
        Port("RateGroupMemberOut", 3, (Argument("ctx", "U32"),)),
    )
    assert mock.components["Top.Driver"].outputs == (Port("tickOut", 1, (Argument("ctx", "U32"),)),)
    assert mock.components["Gnc.Nav"].outputs == ()
    assert mock.components["Gnc.RateGroup"].inputs == (
        Port("CycleIn", 1, (Argument("ctx", "U32"),)),
    )
    assert mock.components["Gnc.Nav"].inputs == (Port("schedIn", 1, (Argument("ctx", "U32"),)),)
    assert mock.components["Top.Driver"].inputs == ()
    assert mock.components["Gnc.Nav"].file.name == "Gnc.fpp"
    assert mock.components["Top.Driver"].file.name == "Top.fpp"
    assert mock.components["Gnc.Nav"].file.is_absolute()


def test_a_serial_output_port_reads_with_no_arguments(tmp_path: Path):
    """A `serial` output port, which has no port type, is an output with no arguments.

    Args:
        tmp_path: where the mock's model is written.
    """
    gnc = edited(
        GNC,
        (
            "    command recv port cmdIn\n",
            "    output port anyOut: serial\n    command recv port cmdIn\n",
        ),
    )

    nav = read(_mock_files(tmp_path, gnc)).components["Gnc.Nav"]

    assert nav.outputs == (Port("anyOut", 1, ()),)


def test_a_parameter_with_a_non_scalar_default_fails_naming_it(tmp_path: Path):
    """A default the reader does not convert raises, naming the parameter.

    Args:
        tmp_path: where the mock's model is written.
    """
    gnc = edited(
        GNC, ("param mounting: Vector3", "param mounting: Vector3 default [1.0, 0.0, 0.0]")
    )

    with pytest.raises(ValueError, match="mounting"):
        read(_mock_files(tmp_path, gnc))


def test_a_model_fpp_rejects_fails_with_its_stderr(tmp_path: Path):
    """`to-json`'s refusal raises with what it printed.

    Args:
        tmp_path: where the mock's model is written.
    """
    gnc = edited(GNC, ("instance nav: Nav", "instance nav: Navigator"))

    with pytest.raises(RuntimeError, match="Navigator"):
        read(_mock_files(tmp_path, gnc))


@pytest.mark.parametrize(
    "key", ["componentInstanceMap", "componentMap", "topologyMap", "typeMap", "valueMap"]
)
def test_a_renamed_analysis_key_fails_the_read(tmp_path: Path, key: str):
    """`parse` on output with a top-level analysis key it reads renamed raises, naming the key.

    Args:
        tmp_path: where the mock's model and `to-json`'s output are written.
        key: the analysis key renamed.
    """
    out = tmp_path / "out"
    model = tmp_path / "model"
    out.mkdir()
    model.mkdir()
    command = [str(_FPP), "to-json", "-d", str(out), *map(str, _mock_files(model))]
    subprocess.run(command, check=True, capture_output=True)
    analysis = out / "fpp-analysis.json"
    document = json.loads(analysis.read_text())
    document["analysis"][f"{key}Renamed"] = document["analysis"].pop(key)
    analysis.write_text(json.dumps(document))

    with pytest.raises(KeyError, match=key):
        parse(out)
