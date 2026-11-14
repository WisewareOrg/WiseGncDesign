"""The dictionary against a toy component's, generated from FPP alone: names and types.

Needs the F´ framework clone `just _sync` fetches, not an F´ build.
"""

from pathlib import Path

import numpy as np
import pytest

from ground.dictionary import Dictionary

TOY = """\
module Toy {

  enum Mode {
    slow
    fast
  }

  passive component Toy {

    @ Sets the toy
    sync command setToy(
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


def _toy(directory: Path, toy: str = TOY, extra: str = EXTRA) -> Dictionary:
    """The toy's dictionary, its model written into `directory`, instanced as `toy`.

    Args:
        directory: where the toy's `.fpp` and the `.fppi` it includes are written.
        toy: the component model.
        extra: the included group.

    Returns:
        The dictionary `from_component` generates.
    """
    (directory / "Toy.fpp").write_text(toy)
    (directory / "Extra.fppi").write_text(extra)
    return Dictionary.from_component([directory / "Toy.fpp"], "Toy.Toy", instance="toy")


@pytest.fixture
def toy(tmp_path: Path) -> Dictionary:
    """The toy's dictionary.

    Args:
        tmp_path: where the toy's model is written.

    Returns:
        The dictionary.
    """
    return _toy(tmp_path)


def test_from_component_writes_nothing_beside_the_model_and_generates_once_per_content(
    tmp_path: Path,
):
    """The deployment is never written in the model's directory; a second call is the cached one.

    Args:
        tmp_path: where the toy's model is written.
    """
    first = _toy(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["Extra.fppi", "Toy.fpp"]
    assert _toy(tmp_path) is first
    assert first.metadata["deploymentName"] == "PyToy.PyToy"


def test_from_component_regenerates_when_a_group_beside_the_model_changes(tmp_path: Path):
    """An edited `.fppi` the component includes gives a new dictionary with the edit.

    Args:
        tmp_path: where the toy's model is written.
    """
    before = _toy(tmp_path)

    after = _toy(tmp_path, extra=EXTRA.replace("extra", "other"))

    assert after is not before
    assert "other" in after.entries("toy")["channels"]
    assert "extra" not in after.entries("toy")["channels"]


def test_from_component_raises_with_the_tool_s_error_for_a_bad_model(tmp_path: Path):
    """A model `fpp-to-dict` rejects raises, naming the component and carrying the tool's stderr.

    Args:
        tmp_path: where the toy's model is written.
    """
    with pytest.raises(RuntimeError, match=r"(?s)rejected Toy\.Toy.*symbol Missing"):
        _toy(tmp_path, toy=TOY.replace("telemetry count: U8", "telemetry count: Missing"))


def test_every_dictionary_carries_f_prime_s_command_responses(toy: Dictionary):
    """A Python build's dictionary has `Fw.CmdResponse`'s constants, from `Interfaces.fpp`.

    Args:
        toy: the toy's dictionary.
    """
    assert toy.responses == {
        "OK": 0,
        "INVALID_OPCODE": 1,
        "VALIDATION_ERROR": 2,
        "FORMAT_ERROR": 3,
        "EXECUTION_ERROR": 4,
        "BUSY": 5,
        "CLEARED": 6,
        "DISPATCHED_UNTRACKED": 7,
    }


def test_arguments_are_typed_as_f_prime_s_handler_gets_them(toy: Dictionary):
    """An F32 as F32 holds it, a bool as a bool, an enum by name, an array as an array.

    Args:
        toy: the toy's dictionary.
    """
    args = toy.arguments("toy.setToy", ARGS)

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
    toy: Dictionary, args: dict, match: str
):
    """Missing arguments, or one that does not fit its type, raise naming it.

    Args:
        toy: the toy's dictionary.
        args: the arguments.
        match: what the error names.
    """
    with pytest.raises(ValueError, match=match):
        toy.arguments("toy.setToy", args)


def test_a_command_with_a_parameter_type_not_coded_loads_and_refuses_its_arguments(
    tmp_path: Path,
):
    """A string parameter does not stop the load; typing that command's arguments is refused.

    Args:
        tmp_path: where the toy's model is written.
    """
    labelled = _toy(
        tmp_path,
        toy=TOY.replace("    @ Sets", "    sync command label(note: string)\n\n    @ Sets"),
    )

    assert labelled.command("toy.label").types is None
    with pytest.raises(ValueError, match=r"toy\.label has a parameter type .* does not code"):
        labelled.arguments("toy.label", {"note": "hello"})


def test_a_mistyped_name_is_refused_naming_it(toy: Dictionary):
    """A channel or command the dictionary lacks raises `KeyError` naming it.

    Args:
        toy: the toy's dictionary.
    """
    with pytest.raises(KeyError, match="'toy.gian'"):
        toy.channel("toy.gian")
    with pytest.raises(KeyError, match="'toy.setTyo'"):
        toy.command("toy.setTyo")
    with pytest.raises(KeyError, match="'toy.setTyo'"):
        toy.arguments("toy.setTyo", ARGS)


def test_values_in_the_channel_s_type_come_back_in_one_batch_with_their_units(toy: Dictionary):
    """Arrays come back (N, *shape), a bool as 1.0, an enum as its name; units are the format's.

    Args:
        toy: the toy's dictionary.
    """
    offset, mounting = toy.channel("toy.offset"), toy.channel("toy.mounting")

    np.testing.assert_array_equal(
        offset.from_raw(np.array([[1, 2, 3], [4, 5, 6]], ">f8")), [[1, 2, 3], [4, 5, 6]]
    )
    np.testing.assert_array_equal(mounting.from_raw(MOUNTING[None].astype(">f8"))[0], MOUNTING)
    assert toy.channel("toy.enabled").from_raw(np.array([0xFF, 0], "u1")).tolist() == [1.0, 0.0]
    assert toy.channel("toy.mode").from_raw(np.array([1, 0], ">i4")).tolist() == ["fast", "slow"]
    assert offset.from_raw(np.empty((0, 3), ">f8")).shape == (0, 3)
    assert [offset.units, mounting.units, toy.channel("toy.extra").units] == ["m", "", "s"]
    assert toy.channels_by_id[offset.id] is offset


def test_an_enum_value_that_is_no_constant_fails_naming_the_channel(toy: Dictionary):
    """A raw enum value outside the enum's constants raises, naming the channel.

    Args:
        toy: the toy's dictionary.
    """
    with pytest.raises(ValueError, match=r"channel toy\.mode has no constant 7"):
        toy.channel("toy.mode").from_raw(np.array([7], ">i4"))


def test_written_values_are_held_to_the_channel_s_type(toy: Dictionary):
    """Values a Python algorithm writes come back as the serialized ones do, an F32 truncated.

    Args:
        toy: the toy's dictionary.
    """
    offset = toy.channel("toy.offset")

    np.testing.assert_array_equal(
        offset.pack_many([np.array([1.0, 2.0, 3.0]), [4, 5, 6]]), [[1, 2, 3], [4, 5, 6]]
    )
    np.testing.assert_array_equal(toy.channel("toy.mounting").pack_many([MOUNTING])[0], MOUNTING)
    assert toy.channel("toy.enabled").pack_many([True, False]).tolist() == [1.0, 0.0]
    assert toy.channel("toy.mode").pack_many(["slow"]).tolist() == ["slow"]
    assert toy.channel("toy.count").pack_many([np.uint8(7), 255, 0]).tolist() == [7.0, 255.0, 0.0]
    assert toy.channel("toy.gain").pack_many([2, 0.1]).tolist() == [2.0, float(np.float32(0.1))]
    assert offset.pack_many([]).shape == (0, 3)
    assert toy.channel("toy.mode").pack_many([]).shape == (0,)


@pytest.mark.parametrize(
    ("channel", "values"),
    [
        ("toy.gain", [0.5, None]),
        ("toy.gain", ["1.5"]),
        ("toy.gain", [True]),
        ("toy.gain", [np.array([1.0, 2.0, 3.0])]),
        ("toy.offset", [1.0]),
        ("toy.offset", [[1.0, 2.0]]),
        ("toy.offset", [[1.0, 2.0, 3.0], [1.0, 2.0]]),
        ("toy.mounting", [np.eye(3)[0]]),
        ("toy.count", [1.5]),
        ("toy.count", [300]),
        ("toy.count", [-1]),
        ("toy.count", [2**70]),
        ("toy.enabled", [1]),
        ("toy.mode", ["standby"]),
        ("toy.mode", [None]),
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
    toy: Dictionary, channel: str, values: list
):
    """A value F´'s packing would reject fails the batch, naming the channel.

    Args:
        toy: the toy's dictionary.
        channel: the channel written.
        values: its writes, one of them bad.
    """
    with pytest.raises(ValueError, match=rf"channel {channel} "):
        toy.channel(channel).pack_many(values)


def test_a_channel_of_a_type_not_coded_is_refused_at_load_naming_channel_and_type(
    tmp_path: Path,
):
    """A struct channel fails the dictionary's load, naming the channel and its type.

    Args:
        tmp_path: where the toy's model is written.
    """
    toy = TOY.replace("  passive", "  struct Pair { a: F64, b: F64 }\n\n  passive")
    toy = toy.replace("telemetry count: U8", "telemetry count: Pair")

    with pytest.raises(ValueError, match=r"channel toy\.count has type Toy\.Pair"):
        _toy(tmp_path, toy=toy)


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
    assert before in TOY

    changed = _toy(tmp_path / "b", toy=TOY.replace(before, after))

    assert _toy(tmp_path / "a").entries("toy") != changed.entries("toy")


def test_entries_are_equal_when_only_ids_and_opcodes_differ(tmp_path: Path):
    """A channel ID and an opcode set by hand leave `entries` unchanged.

    Args:
        tmp_path: where the toy's model is written.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    toy = TOY.replace('format "{} rad"', 'id 0x20 format "{} rad"')
    toy = toy.replace("      count: U8\n    )", "      count: U8\n    ) opcode 5")
    moved = _toy(tmp_path / "b", toy=toy)
    original = _toy(tmp_path / "a")

    assert moved.channel("toy.gain").id != original.channel("toy.gain").id
    assert moved.entries("toy") == original.entries("toy")
