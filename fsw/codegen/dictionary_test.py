"""The dictionary against a mock component's, generated from FPP alone: names and types.

Needs the F´ framework clone `just _sync` fetches. Holding each GNC instance's generated dictionary
to WiseFsw's also needs the deployment `just fsw` builds, and skips without it.
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.dictionary import Dictionary
from fsw.codegen.fpp_model import Instance
from fsw.mock import ARGS


def test_from_component_writes_nothing_beside_the_model_and_generates_once_per_content(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """The deployment is never written in the model's directory; a second call is the cached one.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    first = render_mock(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["Extra.fppi", "Mock.fpp"]
    assert render_mock(tmp_path) is first
    assert first.metadata["deploymentName"] == "PyMock.PyMock"


def test_from_component_regenerates_when_a_group_beside_the_model_changes(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """An edited `.fppi` the component includes gives a new dictionary with the edit.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    before = render_mock(tmp_path)

    after = render_mock(tmp_path, extra=(("extra", "other"),))

    assert after is not before
    assert "other" in after.entries("mock")["channels"]
    assert "extra" not in after.entries("mock")["channels"]


def test_from_component_raises_with_the_tool_s_error_for_a_bad_model(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """A model `fpp-to-dict` rejects raises, naming the component and carrying the tool's stderr.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    with pytest.raises(RuntimeError, match=r"(?s)rejected Mock\.Mock.*symbol Missing"):
        render_mock(tmp_path, ("telemetry count: U8", "telemetry count: Missing"))


def test_arguments_are_typed_as_f_prime_s_handler_gets_them(mock_dictionary: Dictionary):
    """An F32 as F32 holds it, a bool as a bool, an enum by name, an array as an array.

    Args:
        mock_dictionary: the mock's dictionary.
    """
    args = mock_dictionary.arguments("mock.setMock", ARGS)

    assert list(args) == ["gain", "enabled", "mode", "offset", "mounting", "count"]
    assert args["gain"] == float(np.float32(0.1))
    assert args["gain"] != 0.1
    assert args["enabled"] is True
    assert args["mode"] == "fast"
    assert isinstance(args["offset"], np.ndarray)
    np.testing.assert_array_equal(args["offset"], ARGS["offset"])
    np.testing.assert_array_equal(args["mounting"], ARGS["mounting"])
    assert args["count"] == 7


@pytest.mark.parametrize(
    ("args", "match"),
    [
        ({k: v for k, v in ARGS.items() if k != "mode"}, r"takes \['gain'"),
        (ARGS | {"extra": 1}, r"takes \['gain'"),
        (ARGS | {"offset": [1.0, 2.0]}, "parameter offset"),
    ],
    ids=["missing", "extra", "short-array"],
)
def test_arguments_that_will_not_fit_are_refused_naming_what(
    mock_dictionary: Dictionary, args: dict, match: str
):
    """Missing arguments, or one that does not fit its type, raise naming it.

    Args:
        mock_dictionary: the mock's dictionary.
        args: the arguments.
        match: what the error names.
    """
    with pytest.raises(ValueError, match=match):
        mock_dictionary.arguments("mock.setMock", args)


def test_a_command_with_a_parameter_type_not_coded_loads_and_refuses_its_arguments(
    mock_dictionary: Dictionary,
):
    """A string parameter does not stop the load; typing that command's arguments is refused.

    Args:
        mock_dictionary: the mock's dictionary, whose `label` takes a string.
    """
    assert mock_dictionary.command("mock.label").types is None
    with pytest.raises(ValueError, match=r"mock\.label has a parameter type .* does not code"):
        mock_dictionary.arguments("mock.label", {"note": "hello"})


def test_a_mistyped_name_is_refused_naming_it(mock_dictionary: Dictionary):
    """A channel or command the dictionary lacks raises `KeyError` naming it.

    Args:
        mock_dictionary: the mock's dictionary.
    """
    with pytest.raises(KeyError, match="'mock.gian'"):
        mock_dictionary.channel("mock.gian")
    with pytest.raises(KeyError, match="'mock.setTyo'"):
        mock_dictionary.arguments("mock.setTyo", ARGS)


def test_values_in_the_channel_s_type_come_back_in_one_batch_with_their_units(
    mock_dictionary: Dictionary,
):
    """A bool comes back 1.0 from F´'s true byte; units are the format's; a channel is found by ID.

    Args:
        mock_dictionary: the mock's dictionary.
    """
    mock = mock_dictionary
    offset, mounting = mock.channel("mock.offset"), mock.channel("mock.mounting")

    assert mock.channel("mock.enabled").from_raw(np.array([0xFF, 0], "u1")).tolist() == [1.0, 0.0]
    assert [offset.units, mounting.units, mock.channel("mock.extra").units] == ["m", "", "s"]
    assert mock.channels_by_id[offset.id] is offset


def test_a_channel_s_units_follow_its_placeholder_whatever_the_placeholder_holds(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """A format spec inside the placeholder does not lose the units.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    mock = render_mock(tmp_path, ('format "{} rad"', 'format "{.3f} rad"'))

    assert mock.channel("mock.gain").units == "rad"


def test_an_instance_s_commands_are_its_entries_commands_in_the_dictionary_s_order(
    mock_dictionary: Dictionary,
):
    """`commands` names exactly the commands `entries` lists, each the dictionary's `command`.

    Args:
        mock_dictionary: the mock's dictionary.
    """
    mock = mock_dictionary

    commands = mock.commands("mock")

    assert commands
    assert {c.name for c in commands} == {f"mock.{n}" for n in mock.entries("mock")["commands"]}
    assert all(mock.command(c.name) is c for c in commands)


def test_an_enum_value_that_is_no_constant_fails_naming_the_channel(mock_dictionary: Dictionary):
    """A raw enum value outside the enum's constants raises, naming the channel.

    Args:
        mock_dictionary: the mock's dictionary.
    """
    with pytest.raises(ValueError, match=r"channel mock\.mode has no constant 7"):
        mock_dictionary.channel("mock.mode").from_raw(np.array([7], ">i4"))


def test_written_values_are_held_to_the_channel_s_type(mock_dictionary: Dictionary):
    """Values a Python algorithm writes come back as the serialized ones do, an F32 truncated.

    Args:
        mock_dictionary: the mock's dictionary.
    """
    mock = mock_dictionary
    offset = mock.channel("mock.offset")

    np.testing.assert_array_equal(
        offset.pack_many([np.array([1.0, 2.0, 3.0]), [4, 5, 6]]), [[1, 2, 3], [4, 5, 6]]
    )
    np.testing.assert_array_equal(
        mock.channel("mock.mounting").pack_many([ARGS["mounting"]])[0], ARGS["mounting"]
    )
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
        ("mock.gain", [True]),
        ("mock.offset", [[1.0, 2.0]]),
        ("mock.offset", [[1.0, 2.0, 3.0], [1.0, 2.0]]),
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
        "bool-to-float",
        "short-vector",
        "ragged",
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
    mock_dictionary: Dictionary, channel: str, values: list
):
    """A value F´'s packing would reject fails the batch, naming the channel.

    Args:
        mock_dictionary: the mock's dictionary.
        channel: the channel written.
        values: its writes, one of them bad.
    """
    with pytest.raises(ValueError, match=rf"channel {channel} "):
        mock_dictionary.channel(channel).pack_many(values)


def test_a_channel_of_a_type_not_coded_is_refused_at_load_naming_channel_and_type(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """A struct channel fails the dictionary's load, naming the channel and its type.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    with pytest.raises(ValueError, match=r"channel mock\.count has type Mock\.Pair"):
        render_mock(
            tmp_path,
            ("  passive", "  struct Pair { a: F64, b: F64 }\n\n  passive"),
            ("telemetry count: U8", "telemetry count: Pair"),
        )


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
def test_entries_differ_when_the_contract_does(
    tmp_path: Path, render_mock: Callable[..., Dictionary], before: str, after: str
):
    """Each change to a name, a type, a format or an enum shows in `entries`.

    Args:
        tmp_path: where the two models are written.
        render_mock: renders the mock.
        before: the text the change replaces.
        after: what it becomes.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    changed = render_mock(tmp_path / "b", (before, after))

    assert render_mock(tmp_path / "a").entries("mock") != changed.entries("mock")


def test_entries_are_equal_when_only_ids_and_opcodes_differ(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """A channel ID and an opcode set by hand leave `entries` unchanged.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    moved = render_mock(
        tmp_path / "b",
        ('format "{} rad"', 'id 0x20 format "{} rad"'),
        ("      count: U8\n    )", "      count: U8\n    ) opcode 5"),
    )
    original = render_mock(tmp_path / "a")

    assert moved.channel("mock.gain").id != original.channel("mock.gain").id
    assert moved.entries("mock") == original.entries("mock")


_PARAMETERS = """    param get port prmGetOut
    param set port prmSetOut
    param limit: F32
    param mounting: Gnc.Matrix3
"""
"""Parameters given to the mock, with the ports a component with parameters needs."""


def test_each_parameter_is_listed_by_id_with_its_name(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """The mock's two parameters come by ID, named `mock.<parameter>`; their commands are marked.

    Instanced at base ID 0x2000, the two parameters are 0x2000 and 0x2001.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    mock = render_mock(
        tmp_path, ("    time get port", _PARAMETERS + "    time get port"), base_id=0x2000
    )

    named = {p.name: p for p in mock.parameters_by_id.values()}

    assert sorted(named) == ["mock.limit", "mock.mounting"]
    assert all(mock.parameters_by_id[p.id] is p for p in named.values())
    assert {name: p.id for name, p in named.items()} == {
        "mock.limit": 0x2000,
        "mock.mounting": 0x2001,
    }
    assert mock.command("mock.LIMIT_PRM_SET").kind == "set"
    assert mock.command("mock.LIMIT_PRM_SAVE").kind == "save"
    assert mock.command("mock.setMock").kind == "sync"


def test_a_parameter_of_a_type_not_coded_does_not_stop_the_dictionary_loading(
    tmp_path: Path, render_mock: Callable[..., Dictionary]
):
    """A struct and a string parameter load: no consumer reads a parameter's type.

    Args:
        tmp_path: where the mock's model is written.
        render_mock: renders the mock.
    """
    added = "    param pair: Pair\n    param label: string\n"
    mock = render_mock(
        tmp_path,
        ("  passive", "  struct Pair { a: F64, b: F64 }\n\n  passive"),
        ("    time get port", _PARAMETERS + added + "    time get port"),
    )

    names = {p.name for p in mock.parameters_by_id.values()}

    assert {"mock.pair", "mock.label"} <= names


def test_every_gnc_instance_s_generated_dictionary_is_wise_fsw_s_entries_and_parameter_ids(
    fprime_configuration: str,
    dictionary: Dictionary,
    algorithm_instances: Callable[[str], tuple[Instance, ...]],
):
    """Each WiseFsw algorithm instance, in its configuration's generated dictionary, is WiseFsw's.

    The generated dictionary is the one the configuration's Python build flies; it states the
    instance's entries and parameter IDs as WiseFsw does.

    It also fails when an algorithm's `.fpp`, or a group it includes, changed and F´ was not
    rebuilt.

    Args:
        fprime_configuration: the configuration.
        dictionary: the dictionary the configuration's F´ build generated.
        algorithm_instances: gives a configuration's algorithm instances.
    """
    wise_fsw = dictionary
    instances = algorithm_instances(fprime_configuration)
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
    assert Dictionary.from_sub_topology(configuration) is generated
