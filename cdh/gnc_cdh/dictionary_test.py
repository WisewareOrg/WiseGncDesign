"""The dictionary against a toy component's, generated from FPP alone: names, types and bytes.

Needs the F´ framework clone `just _sync` fetches, not an F´ build.
"""

import struct
from pathlib import Path

import numpy as np
import pytest

from gnc_cdh.dictionary import DecodeError, Dictionary

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


def test_a_command_packet_is_f_prime_s_and_decodes_as_f_prime_would(toy: Dictionary):
    """Descriptor, opcode, then big-endian arguments; an F32 is truncated and a bool is 0xFF.

    Args:
        toy: the toy's dictionary.
    """
    packet = toy.encode_command("toy.setToy", ARGS)

    assert packet[:6] == struct.pack(">HI", 0, 0x1000)
    assert packet[6:10] == struct.pack(">f", 0.1)
    assert packet[10] == 0xFF
    assert len(packet) == 6 + 4 + 1 + 4 + 3 * 8 + 9 * 8
    name, args = toy.decode_command(packet, "toy")
    assert name == "setToy"
    assert args["gain"] == float(np.float32(0.1))
    assert args["gain"] != 0.1
    assert args["enabled"] is True
    assert args["mode"] == "fast"
    np.testing.assert_array_equal(args["offset"], ARGS["offset"])
    np.testing.assert_array_equal(args["mounting"], MOUNTING)


@pytest.mark.parametrize(
    ("change", "response"),
    [
        (lambda packet: packet[:5], "VALIDATION_ERROR"),
        (lambda packet: struct.pack(">H", 1) + packet[2:], "VALIDATION_ERROR"),
        (lambda packet: packet[:6] + packet[6:-1], "FORMAT_ERROR"),
        (lambda packet: packet + b"\0", "FORMAT_ERROR"),
        (lambda packet: packet[:10] + b"\x01" + packet[11:], "FORMAT_ERROR"),
        (lambda packet: packet[:11] + struct.pack(">i", 7) + packet[15:], "FORMAT_ERROR"),
    ],
    ids=["short", "not-a-command", "truncated", "bytes-left-over", "bool-not-0xff", "no-constant"],
)
def test_a_malformed_packet_earns_the_response_f_prime_gives_it(
    toy: Dictionary, change: object, response: str
):
    """Each malformed packet raises `DecodeError` carrying the dispatcher's or autocoder's response.

    Args:
        toy: the toy's dictionary.
        change: makes the malformed packet from a good one.
        response: the response it earns.
    """
    with pytest.raises(DecodeError) as error:
        toy.decode_command(change(toy.encode_command("toy.setToy", ARGS)), "toy")

    assert error.value.response == response


def test_a_command_of_another_instance_is_an_invalid_opcode(toy: Dictionary):
    """An opcode the receiving instance does not own earns `INVALID_OPCODE`.

    Args:
        toy: the toy's dictionary.
    """
    with pytest.raises(DecodeError) as error:
        toy.decode_command(toy.encode_command("toy.setToy", ARGS), "nav")

    assert error.value.response == "INVALID_OPCODE"


@pytest.mark.parametrize(
    ("args", "match"),
    [
        ({k: v for k, v in ARGS.items() if k != "mode"}, r"takes \['gain'"),
        (ARGS | {"offset": [1.0, 2.0]}, "parameter offset"),
        (ARGS | {"gain": None}, "parameter gain"),
        (ARGS | {"mode": "standby"}, "parameter mode"),
    ],
    ids=["missing", "short-array", "none", "no-constant"],
)
def test_a_command_that_will_not_pack_is_refused_naming_what(
    toy: Dictionary, args: dict, match: str
):
    """Missing arguments, or one that does not pack into its type, raise naming it.

    Args:
        toy: the toy's dictionary.
        args: the arguments.
        match: what the error names.
    """
    with pytest.raises(ValueError, match=match):
        toy.encode_command("toy.setToy", args)


def test_serialized_channels_decode_in_one_batch_with_their_units(toy: Dictionary):
    """Arrays come back (N, *shape), a bool as 1.0, an enum as its name; units are the format's.

    Args:
        toy: the toy's dictionary.
    """
    offset, mounting = toy.channel("toy.offset"), toy.channel("toy.mounting")

    np.testing.assert_array_equal(
        offset.decode_many([struct.pack(">3d", 1, 2, 3), struct.pack(">3d", 4, 5, 6)]),
        [[1, 2, 3], [4, 5, 6]],
    )
    np.testing.assert_array_equal(mounting.decode(struct.pack(">9d", *range(9))), MOUNTING)
    assert toy.channel("toy.enabled").decode(b"\xff") == 1.0
    assert toy.channel("toy.mode").decode(struct.pack(">i", 1)) == "fast"
    assert toy.channel("toy.gain").decode(struct.pack(">f", 0.5)) == 0.5
    assert [offset.units, mounting.units, toy.channel("toy.extra").units] == ["m", "", "s"]
    assert toy.channels_by_id[offset.id] is offset


def test_written_values_are_held_to_the_channel_s_type(toy: Dictionary):
    """Values a Python algorithm writes come back as the serialized ones do.

    Args:
        toy: the toy's dictionary.
    """
    vectors = [np.array([1.0, 2.0, 3.0]), [4, 5, 6]]

    np.testing.assert_array_equal(
        toy.channel("toy.offset").decode_many(vectors), [[1, 2, 3], [4, 5, 6]]
    )
    np.testing.assert_array_equal(toy.channel("toy.mounting").decode(MOUNTING), MOUNTING)
    assert toy.channel("toy.enabled").decode(True) == 1.0
    assert toy.channel("toy.mode").decode("slow") == "slow"
    assert toy.channel("toy.count").decode(np.uint8(7)) == 7.0
    assert toy.channel("toy.gain").decode(2) == 2.0


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
        toy.channel(channel).decode_many(values)


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
    toy = toy.replace(
        "      mounting: Gnc.Matrix3\n    )", "      mounting: Gnc.Matrix3\n    ) opcode 5"
    )
    moved = _toy(tmp_path / "b", toy=toy)
    original = _toy(tmp_path / "a")

    assert moved.channel("toy.gain").id != original.channel("toy.gain").id
    assert moved.entries("toy") == original.entries("toy")
