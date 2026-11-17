"""The dictionary against a mock component's, generated from FPP alone: names and types.

Needs the F´ framework clone `just _sync` fetches. Holding each GNC instance's generated dictionary
to WiseFsw's also needs the deployment `just fsw` builds, and skips without it.
"""

from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.fpp_model import Instance
from ground.dictionary import Dictionary

MOCK = """\
module Mock {

  enum Mode {
    slow
    fast
  }

  passive component Mock {

    @ Sets the mock
    sync command setMock(
      gain: F32
      enabled: bool
      mode: Mode
      offset: Gnc.Vector3
      mounting: Gnc.Matrix3
      count: U8
    )

    telemetry gain: F32 format "{} rad"
    telemetry enabled: bool
    telemetry mode: Mode
    telemetry count: U8
    telemetry offset: Gnc.Vector3 format "{} m"
    telemetry mounting: Gnc.Matrix3

    include "Extra.fppi"

    time get port timeCaller
    telemetry port tlmOut
    command reg port cmdRegOut
    command recv port cmdIn
    command resp port cmdResponseOut

  }

}
"""

EXTRA = 'telemetry extra: F64 format "{} s"\n'

MOUNTING = np.arange(9.0).reshape(3, 3)

ARGS = {
    "gain": 0.1,
    "enabled": True,
    "mode": "fast",
    "offset": [1.0, 2.0, 3.0],
    "mounting": MOUNTING,
    "count": 7,
}


def _mock(
    directory: Path, mock: str = MOCK, extra: str = EXTRA, base_id: int = 0x1000
) -> Dictionary:
    """The mock's dictionary, its model written into `directory`, instanced as `mock`.

    Args:
        directory: where the mock's `.fpp` and the `.fppi` it includes are written.
        mock: the component model.
        extra: the included group.
        base_id: the instance's base ID.

    Returns:
        The dictionary `from_component` generates.
    """
    (directory / "Mock.fpp").write_text(mock)
    (directory / "Extra.fppi").write_text(extra)
    return Dictionary.from_component(
        [directory / "Mock.fpp"], Instance("Mock.mock", "Mock.Mock", base_id)
    )


@pytest.fixture
def mock(tmp_path: Path) -> Dictionary:
    """The mock's dictionary.

    Args:
        tmp_path: where the mock's model is written.

    Returns:
        The dictionary.
    """
    return _mock(tmp_path)


def test_from_component_writes_nothing_beside_the_model_and_generates_once_per_content(
    tmp_path: Path,
):
    """The deployment is never written in the model's directory; a second call is the cached one.

    Args:
        tmp_path: where the mock's model is written.
    """
    first = _mock(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["Extra.fppi", "Mock.fpp"]
    assert _mock(tmp_path) is first
    assert first.metadata["deploymentName"] == "PyMock.PyMock"


def test_from_component_regenerates_when_a_group_beside_the_model_changes(tmp_path: Path):
    """An edited `.fppi` the component includes gives a new dictionary with the edit.

    Args:
        tmp_path: where the mock's model is written.
    """
    before = _mock(tmp_path)

    after = _mock(tmp_path, extra=EXTRA.replace("extra", "other"))

    assert after is not before
    assert "other" in after.entries("mock")["channels"]
    assert "extra" not in after.entries("mock")["channels"]


def test_from_component_raises_with_the_tool_s_error_for_a_bad_model(tmp_path: Path):
    """A model `fpp-to-dict` rejects raises, naming the component and carrying the tool's stderr.

    Args:
        tmp_path: where the mock's model is written.
    """
    with pytest.raises(RuntimeError, match=r"(?s)rejected Mock\.Mock.*symbol Missing"):
        _mock(tmp_path, mock=MOCK.replace("telemetry count: U8", "telemetry count: Missing"))


def test_every_dictionary_carries_f_prime_s_command_responses(mock: Dictionary):
    """A Python build's dictionary has `Fw.CmdResponse`'s constants, from `Interfaces.fpp`.

    Args:
        mock: the mock's dictionary.
    """
    assert mock.responses == {
        "OK": 0,
        "INVALID_OPCODE": 1,
        "VALIDATION_ERROR": 2,
        "FORMAT_ERROR": 3,
        "EXECUTION_ERROR": 4,
        "BUSY": 5,
        "CLEARED": 6,
        "DISPATCHED_UNTRACKED": 7,
    }


def test_arguments_are_typed_as_f_prime_s_handler_gets_them(mock: Dictionary):
    """An F32 as F32 holds it, a bool as a bool, an enum by name, an array as an array.

    Args:
        mock: the mock's dictionary.
    """
    args = mock.arguments("mock.setMock", ARGS)

    assert list(args) == ["gain", "enabled", "mode", "offset", "mounting", "count"]
    assert args["gain"] == float(np.float32(0.1))
    assert args["gain"] != 0.1
    assert args["enabled"] is True
    assert args["mode"] == "fast"
    assert isinstance(args["offset"], np.ndarray)
    np.testing.assert_array_equal(args["offset"], ARGS["offset"])
    np.testing.assert_array_equal(args["mounting"], MOUNTING)
    assert args["count"] == 7


@pytest.mark.parametrize(
    ("args", "match"),
    [
        ({k: v for k, v in ARGS.items() if k != "mode"}, r"takes \['gain'"),
        (ARGS | {"extra": 1}, r"takes \['gain'"),
        (ARGS | {"offset": [1.0, 2.0]}, "parameter offset"),
        (ARGS | {"gain": None}, "parameter gain"),
        (ARGS | {"mode": "standby"}, "parameter mode"),
        (ARGS | {"count": 300}, "parameter count"),
        (ARGS | {"count": -1}, "parameter count"),
    ],
    ids=["missing", "extra", "short-array", "none", "no-constant", "above-u8", "below-u8"],
)
def test_arguments_that_will_not_fit_are_refused_naming_what(
    mock: Dictionary, args: dict, match: str
):
    """Missing arguments, or one that does not fit its type, raise naming it.

    Args:
        mock: the mock's dictionary.
        args: the arguments.
        match: what the error names.
    """
    with pytest.raises(ValueError, match=match):
        mock.arguments("mock.setMock", args)


def test_a_command_with_a_parameter_type_not_coded_loads_and_refuses_its_arguments(
    tmp_path: Path,
):
    """A string parameter does not stop the load; typing that command's arguments is refused.

    Args:
        tmp_path: where the mock's model is written.
    """
    labelled = _mock(
        tmp_path,
        mock=MOCK.replace("    @ Sets", "    sync command label(note: string)\n\n    @ Sets"),
    )

    assert labelled.command("mock.label").types is None
    with pytest.raises(ValueError, match=r"mock\.label has a parameter type .* does not code"):
        labelled.arguments("mock.label", {"note": "hello"})


def test_a_mistyped_name_is_refused_naming_it(mock: Dictionary):
    """A channel or command the dictionary lacks raises `KeyError` naming it.

    Args:
        mock: the mock's dictionary.
    """
    with pytest.raises(KeyError, match="'mock.gian'"):
        mock.channel("mock.gian")
    with pytest.raises(KeyError, match="'mock.setTyo'"):
        mock.command("mock.setTyo")
    with pytest.raises(KeyError, match="'mock.setTyo'"):
        mock.arguments("mock.setTyo", ARGS)


def test_values_in_the_channel_s_type_come_back_in_one_batch_with_their_units(mock: Dictionary):
    """Arrays come back (N, *shape), a bool as 1.0, an enum as its name; units are the format's.

    Args:
        mock: the mock's dictionary.
    """
    offset, mounting = mock.channel("mock.offset"), mock.channel("mock.mounting")

    np.testing.assert_array_equal(
        offset.from_raw(np.array([[1, 2, 3], [4, 5, 6]], ">f8")), [[1, 2, 3], [4, 5, 6]]
    )
    np.testing.assert_array_equal(mounting.from_raw(MOUNTING[None].astype(">f8"))[0], MOUNTING)
    assert mock.channel("mock.enabled").from_raw(np.array([0xFF, 0], "u1")).tolist() == [1.0, 0.0]
    assert mock.channel("mock.mode").from_raw(np.array([1, 0], ">i4")).tolist() == ["fast", "slow"]
    assert offset.from_raw(np.empty((0, 3), ">f8")).shape == (0, 3)
    assert [offset.units, mounting.units, mock.channel("mock.extra").units] == ["m", "", "s"]
    assert mock.channels_by_id[offset.id] is offset


def test_an_enum_value_that_is_no_constant_fails_naming_the_channel(mock: Dictionary):
    """A raw enum value outside the enum's constants raises, naming the channel.

    Args:
        mock: the mock's dictionary.
    """
    with pytest.raises(ValueError, match=r"channel mock\.mode has no constant 7"):
        mock.channel("mock.mode").from_raw(np.array([7], ">i4"))


def test_written_values_are_held_to_the_channel_s_type(mock: Dictionary):
    """Values a Python algorithm writes come back as the serialized ones do, an F32 truncated.

    Args:
        mock: the mock's dictionary.
    """
    offset = mock.channel("mock.offset")

    np.testing.assert_array_equal(
        offset.pack_many([np.array([1.0, 2.0, 3.0]), [4, 5, 6]]), [[1, 2, 3], [4, 5, 6]]
    )
    np.testing.assert_array_equal(mock.channel("mock.mounting").pack_many([MOUNTING])[0], MOUNTING)
    assert mock.channel("mock.enabled").pack_many([True, False]).tolist() == [1.0, 0.0]
    assert mock.channel("mock.mode").pack_many(["slow"]).tolist() == ["slow"]
    assert mock.channel("mock.count").pack_many([np.uint8(7), 255, 0]).tolist() == [7.0, 255.0, 0.0]
    assert mock.channel("mock.gain").pack_many([2, 0.1]).tolist() == [2.0, float(np.float32(0.1))]
    assert offset.pack_many([]).shape == (0, 3)
    assert mock.channel("mock.mode").pack_many([]).shape == (0,)


@pytest.mark.parametrize(
    ("channel", "values"),
    [
        ("mock.gain", [0.5, None]),
        ("mock.gain", ["1.5"]),
        ("mock.gain", [True]),
        ("mock.gain", [np.array([1.0, 2.0, 3.0])]),
        ("mock.offset", [1.0]),
        ("mock.offset", [[1.0, 2.0]]),
        ("mock.offset", [[1.0, 2.0, 3.0], [1.0, 2.0]]),
        ("mock.mounting", [np.eye(3)[0]]),
        ("mock.count", [1.5]),
        ("mock.count", [300]),
        ("mock.count", [-1]),
        ("mock.count", [2**70]),
        ("mock.enabled", [1]),
        ("mock.mode", ["standby"]),
        ("mock.mode", [None]),
    ],
    ids=[
        "none",
        "string",
        "bool-to-float",
        "vector-to-scalar",
        "scalar-to-vector",
        "short-vector",
        "ragged",
        "vector-to-matrix",
        "float-to-integer",
        "above-u8",
        "below-u8",
        "above-i64",
        "integer-to-bool",
        "no-constant",
        "none-to-enum",
    ],
)
def test_a_written_value_that_will_not_fit_fails_naming_the_channel(
    mock: Dictionary, channel: str, values: list
):
    """A value F´'s packing would reject fails the batch, naming the channel.

    Args:
        mock: the mock's dictionary.
        channel: the channel written.
        values: its writes, one of them bad.
    """
    with pytest.raises(ValueError, match=rf"channel {channel} "):
        mock.channel(channel).pack_many(values)


def test_a_channel_of_a_type_not_coded_is_refused_at_load_naming_channel_and_type(
    tmp_path: Path,
):
    """A struct channel fails the dictionary's load, naming the channel and its type.

    Args:
        tmp_path: where the mock's model is written.
    """
    mock = MOCK.replace("  passive", "  struct Pair { a: F64, b: F64 }\n\n  passive")
    mock = mock.replace("telemetry count: U8", "telemetry count: Pair")

    with pytest.raises(ValueError, match=r"channel mock\.count has type Mock\.Pair"):
        _mock(tmp_path, mock=mock)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("telemetry gain:", "telemetry gains:"),
        ('gain: F32 format "{} rad"', 'gain: F64 format "{} rad"'),
        ('"{} rad"', '"{} deg"'),
        ("      enabled: bool", "      armed: bool"),
        ("    fast\n  }", "    fast\n    standby\n  }"),
    ],
    ids=["channel-renamed", "channel-retyped", "units", "parameter-renamed", "constant-added"],
)
def test_entries_differ_when_the_contract_does(tmp_path: Path, before: str, after: str):
    """Each change to a name, a type, a format or an enum shows in `entries`.

    Args:
        tmp_path: where the two models are written.
        before: the text the change replaces.
        after: what it becomes.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert before in MOCK

    changed = _mock(tmp_path / "b", mock=MOCK.replace(before, after))

    assert _mock(tmp_path / "a").entries("mock") != changed.entries("mock")


def test_entries_are_equal_when_only_ids_and_opcodes_differ(tmp_path: Path):
    """A channel ID and an opcode set by hand leave `entries` unchanged.

    Args:
        tmp_path: where the mock's model is written.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    mock = MOCK.replace('format "{} rad"', 'id 0x20 format "{} rad"')
    mock = mock.replace("      count: U8\n    )", "      count: U8\n    ) opcode 5")
    moved = _mock(tmp_path / "b", mock=mock)
    original = _mock(tmp_path / "a")

    assert moved.channel("mock.gain").id != original.channel("mock.gain").id
    assert moved.entries("mock") == original.entries("mock")


_PARAMETERS = """    param get port prmGetOut
    param set port prmSetOut
    param limit: F32
    param mounting: Gnc.Matrix3
"""
"""Parameters given to the mock, with the ports a component with parameters needs."""


def test_each_parameter_is_listed_by_id_with_its_name(tmp_path: Path):
    """The mock's two parameters come by ID, named `mock.<parameter>`; their commands are marked.

    Args:
        tmp_path: where the mock's model is written.
    """
    mock = _mock(
        tmp_path, mock=MOCK.replace("    time get port", _PARAMETERS + "    time get port")
    )

    named = {p.name: p for p in mock.parameters_by_id.values()}

    assert sorted(named) == ["mock.limit", "mock.mounting"]
    assert all(mock.parameters_by_id[p.id] is p for p in named.values())
    assert mock.command("mock.LIMIT_PRM_SET").kind == "set"
    assert mock.command("mock.LIMIT_PRM_SAVE").kind == "save"
    assert mock.command("mock.setMock").kind == "sync"


def test_the_instance_s_parameters_are_numbered_from_its_base_id(tmp_path: Path):
    """Instanced at base ID 0x2000, the mock's two parameters are 0x2000 and 0x2001.

    Args:
        tmp_path: where the mock's model is written.
    """
    mock = MOCK.replace("    time get port", _PARAMETERS + "    time get port")

    dictionary = _mock(tmp_path, mock=mock, base_id=0x2000)

    named = dictionary.parameters_by_id.values()
    assert {p.name: p.id for p in named} == {"mock.limit": 0x2000, "mock.mounting": 0x2001}


def test_a_parameter_of_a_type_not_coded_does_not_stop_the_dictionary_loading(tmp_path: Path):
    """A struct and a string parameter load: no consumer reads a parameter's type.

    Args:
        tmp_path: where the mock's model is written.
    """
    mock = MOCK.replace("  passive", "  struct Pair { a: F64, b: F64 }\n\n  passive")
    added = "    param pair: Pair\n    param label: string\n"
    mock = mock.replace("    time get port", _PARAMETERS + added + "    time get port")

    names = {p.name for p in _mock(tmp_path, mock=mock).parameters_by_id.values()}

    assert {"mock.pair", "mock.label"} <= names


def test_the_algorithm_instances_are_the_gnc_instances_of_an_algorithm_it_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A GNC instance is one of the dictionary's when it has entries there and is an algorithm's.

    The mock's dictionary holds `PyMock.mock`; a second instance of its component has no entries in
    it, and while the mock is no algorithm's component neither instance is.

    Args:
        tmp_path: where the mock's model is written.
        monkeypatch: gives the GNC sub-topologies the mock's instances, and the algorithms its
            component.
    """
    mock = _mock(tmp_path)
    held = Instance("PyMock.mock", "Mock.Mock", 0x1000)
    absent = Instance("PyMock.other", "Mock.Mock", 0x2000)
    monkeypatch.setattr("ground.dictionary.gnc_instances", lambda: (held, absent))
    monkeypatch.setattr("ground.dictionary.algorithm_components", lambda: {"Mock.Mock"})

    assert mock.algorithm_instances() == (held,)
    monkeypatch.setattr("ground.dictionary.algorithm_components", lambda: set())
    assert mock.algorithm_instances() == ()


def test_every_gnc_instance_s_generated_dictionary_is_wise_fsw_s_entries_and_parameter_ids(
    dictionary: Dictionary,
):
    """Each WiseFsw algorithm instance, in its configuration's generated dictionary, is WiseFsw's.

    The generated dictionary is the one the configuration's Python build flies; it states the
    instance's entries and parameter IDs as WiseFsw does.

    It also fails when an algorithm's `.fpp`, or a group it includes, changed and F´ was not
    rebuilt.

    Args:
        dictionary: the dictionary the configuration's F´ build generated.
    """
    wise_fsw = dictionary
    instances = wise_fsw.algorithm_instances()
    assert instances

    def ids(dictionary: Dictionary, instance: str) -> dict[str, int]:
        """Each of an instance's parameters' ID.

        Args:
            dictionary: a dictionary.
            instance: the instance's unqualified name.

        Returns:
            ID by `<instance>.<parameter>`.
        """
        named = dictionary.parameters_by_id.values()
        return {p.name: p.id for p in named if p.name.startswith(f"{instance}.")}

    for instance in instances:
        generated = Dictionary.from_sub_topology(instance.name.split(".", 1)[0])
        short = instance.name.rsplit(".", 1)[-1]
        expected = wise_fsw.entries(short)
        assert expected["channels"] or expected["commands"] or ids(wise_fsw, short), instance.name
        assert generated.entries(short) == expected, instance.name
        assert ids(generated, short) == ids(wise_fsw, short), instance.name


def test_a_configuration_s_dictionary_is_its_own_deployment_generated_once_per_content(
    configuration: str,
):
    """`from_sub_topology` names its deployment for the configuration and caches it per process.

    Args:
        configuration: the configuration.
    """
    generated = Dictionary.from_sub_topology(configuration)

    assert generated.metadata["deploymentName"] == f"Py{configuration}.Py{configuration}"
    assert generated.algorithm_instances()
    assert Dictionary.from_sub_topology(configuration) is generated
