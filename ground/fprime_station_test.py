"""The F´ ground station: names to command packets, and telemetry bytes to values.

The codec runs against a mock component's dictionary, generated from FPP alone. The packets that
reach the deployment crafted or malformed are made from F´'s own `cmdDisp.CMD_TEST_CMD_1`, which
every deployment has; they need the deployment `just fsw` builds, and skip without it.
"""

import json
import struct
from collections.abc import Callable
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from fsw.codegen.deployment import gnc_instances
from fsw.codegen.dictionary import Dictionary
from fsw.mock import ARGS
from ground.fprime_station import FprimeStation
from lab import dictionary_path
from lab.power_cycle import power_cycle

TEST_COMMAND = "cmdDisp.CMD_TEST_CMD_1"
"""F´'s CommandDispatcher's test command, which takes arguments, in every deployment."""

NS = 1_000_000_000
"""ns per s."""


@pytest.fixture(scope="module")
def mock(mock_dictionary: Dictionary) -> FprimeStation:
    """A station for the mock on no deployment: its codec only.

    Args:
        mock_dictionary: the mock's dictionary.

    Returns:
        The station.
    """
    return FprimeStation(ModuleType("no_deployment"), mock_dictionary)


def test_a_command_packet_is_f_prime_s(mock: FprimeStation, mock_dictionary: Dictionary):
    """Descriptor, opcode, then big-endian arguments; an F32 is truncated and a bool is 0xFF.

    Args:
        mock: the mock's station.
        mock_dictionary: the mock's dictionary, which types the arguments.
    """
    packet = mock.encode_command("mock.setMock", mock_dictionary.arguments("mock.setMock", ARGS))

    assert packet[:6] == struct.pack(">HI", 0, 0x1000)
    assert packet[6:10] == struct.pack(">f", 0.1)
    assert packet[10] == 0xFF
    assert packet[11:15] == struct.pack(">i", 1)
    assert packet[15:39] == struct.pack(">3d", 1.0, 2.0, 3.0)
    assert packet[39:111] == struct.pack(">9d", *range(9))
    assert packet[111:] == bytes([7])


@pytest.mark.parametrize(
    ("name", "args", "error", "match"),
    [
        ("mock.setMock", {k: v for k, v in ARGS.items() if k != "mode"}, KeyError, "'mode'"),
        ("mock.label", {"note": "hello"}, ValueError, r"mock\.label has a parameter type"),
    ],
    ids=["missing-argument", "type-not-coded"],
)
def test_a_command_the_station_cannot_encode_is_refused_naming_what(
    mock: FprimeStation, name: str, args: dict, error: type[BaseException], match: str
):
    """A missing argument, or a parameter of a type not coded, raises naming it.

    Args:
        mock: the mock's station.
        name: the command encoded.
        args: its arguments.
        error: what encoding raises.
        match: what the error names.
    """
    with pytest.raises(error, match=match):
        mock.encode_command(name, args)


def _packet(dictionary: Dictionary, entries: list[tuple[str, tuple[int, int], Any]], descriptor: str = "FW_PACKET_TELEM") -> bytes:
    """An F´ `TlmPacket` as `Svc.TlmChan` sends it.

    Args:
        dictionary: the dictionary that types the packet's fields and its channels.
        entries: each entry's channel name, its time as seconds and microseconds, and its value.
        descriptor: the `ComCfg.Apid` constant the packet's descriptor holds.

    Returns:
        A big-endian descriptor, then each entry's channel ID, `Fw.TimeValue` (time base, context,
        seconds, microseconds) and value bytes.
    """
    constants = dictionary.type("ComCfg.Apid").constants
    assert constants is not None
    packet = np.array(constants[descriptor], dictionary.type("FwPacketDescriptorType").dtype).tobytes()
    for name, (seconds, microseconds), value in entries:
        channel = dictionary.channel(name)
        packet += np.array(channel.id, dictionary.type("FwChanIdType").dtype).tobytes()
        packet += np.array(0, dictionary.type("FwTimeBaseStoreType").dtype).tobytes()
        packet += np.array(0, dictionary.type("FwTimeContextStoreType").dtype).tobytes()
        packet += np.array([seconds, microseconds], ">u4").tobytes()
        packet += np.asarray(value, dtype=channel.type.dtype.base).tobytes()
    return packet


def _downlink(packets: list[bytes]) -> Any:
    """What `FprimeStation.telemetry` gives for these packets, the one place its form is built.

    Args:
        packets: each packet's bytes, oldest first.

    Returns:
        The packets back to back, and each packet's size as native U32.
    """
    return b"".join(packets), np.array([len(packet) for packet in packets], np.uint32).tobytes()


def test_telemetry_packets_become_each_channel_s_tags_and_values_in_one_batch(
    mock: FprimeStation, mock_dictionary: Dictionary
):
    """Arrays come back (N, *shape), an enum as its name, an F32 as F32 holds it; tags are int64 ns.

    The channels' sizes differ, so each entry's length is the channel's, and a channel's entries
    in two packets come back in the order downlinked.

    Args:
        mock: the mock's station.
        mock_dictionary: the mock's dictionary.
    """
    first = _packet(
        mock_dictionary,
        [
            ("mock.gain", (10, 500_000), 0.1),
            ("mock.offset", (10, 500_000), [1, 2, 3]),
            ("mock.mode", (10, 500_001), 1),
        ],
    )
    second = _packet(
        mock_dictionary,
        [("mock.offset", (11, 0), [4, 5, 6]), ("mock.mounting", (11, 0), np.arange(9.0).reshape(3, 3))],
    )

    decoded = mock.decode([_downlink([first, second])])

    assert set(decoded) == {"mock.gain", "mock.offset", "mock.mode", "mock.mounting"}
    times, offsets = decoded["mock.offset"]
    assert times.dtype == np.int64
    assert times.tolist() == [10_500_000_000, 11_000_000_000]
    np.testing.assert_array_equal(offsets, [[1, 2, 3], [4, 5, 6]])
    assert decoded["mock.mode"][0].tolist() == [10_500_001_000]
    assert decoded["mock.mode"][1].tolist() == ["fast"]
    assert decoded["mock.gain"][1].tolist() == [float(np.float32(0.1))]
    np.testing.assert_array_equal(decoded["mock.mounting"][1], [np.arange(9.0).reshape(3, 3)])


def test_decode_takes_the_named_channels_only(mock: FprimeStation, mock_dictionary: Dictionary):
    """`names` keeps those channels, whatever their place in the packet, and no other.

    Args:
        mock: the mock's station.
        mock_dictionary: the mock's dictionary.
    """
    packet = _packet(
        mock_dictionary,
        [("mock.gain", (1, 0), 0.5), ("mock.offset", (1, 0), [1, 2, 3]), ("mock.mode", (1, 0), 1)],
    )

    decoded = mock.decode([_downlink([packet])], ["mock.offset", "mock.mode"])

    assert set(decoded) == {"mock.offset", "mock.mode"}
    np.testing.assert_array_equal(decoded["mock.offset"][1], [[1, 2, 3]])
    assert decoded["mock.mode"][1].tolist() == ["fast"]


def test_several_drains_decode_together_in_order_and_an_empty_drain_adds_nothing(
    mock: FprimeStation, mock_dictionary: Dictionary
):
    """A channel's values across drains come back oldest first; no drain decodes to nothing.

    Args:
        mock: the mock's station.
        mock_dictionary: the mock's dictionary.
    """
    first = _downlink([_packet(mock_dictionary, [("mock.gain", (1, 0), 0.5)])])
    second = _downlink([_packet(mock_dictionary, [("mock.gain", (2, 0), 0.25)])])
    empty = _downlink([])

    times, gains = mock.decode([first, empty, second])["mock.gain"]

    assert times.tolist() == [1_000_000_000, 2_000_000_000]
    assert gains.tolist() == [0.5, 0.25]
    assert mock.decode([empty]) == {}
    assert mock.decode([]) == {}


def _test_command(dictionary: Dictionary) -> bytes:
    """`cmdDisp.CMD_TEST_CMD_1` with an argument of each parameter's type, as the station codes it.

    Args:
        dictionary: the deployment's dictionary.

    Returns:
        The packet.
    """
    command = dictionary.command(TEST_COMMAND)
    assert command.types is not None, f"{TEST_COMMAND} takes parameters of coded types"
    args = {
        param: 1.5 if type_.dtype.kind == "f" else 1 for param, type_ in zip(command.params, command.types, strict=True)
    }
    station = FprimeStation(ModuleType("no_deployment"), dictionary)
    return station.encode_command(TEST_COMMAND, dictionary.arguments(TEST_COMMAND, args))


def _unknown_opcode(configuration: str) -> int:
    """An opcode no instance of the configuration's deployment has.

    Args:
        configuration: the configuration.

    Returns:
        One past the largest opcode.
    """
    document = json.loads(dictionary_path(configuration).read_text())
    return max(c["opcode"] for c in document["commands"]) + 1


def _gnc_writes(writes: list[tuple[str, int, Any]], configuration: str) -> list[tuple[str, int, Any]]:
    """The writes of the configuration's GNC instances among drained ones.

    Args:
        writes: drained writes, as `decoded` gives them.
        configuration: the configuration.

    Returns:
        Those writes, in order, each value as plain lists.
    """
    prefixes = tuple(
        f"{i.name.removeprefix(f'{configuration}.')}."
        for i in gnc_instances()
        if i.name.startswith(f"{configuration}.")
    )
    return [(n, t, np.asarray(v).tolist()) for n, t, v in writes if n.startswith(prefixes)]


@pytest.mark.parametrize(
    ("change", "response"),
    [
        (lambda good, unknown: good[:2] + unknown.to_bytes(4, "big") + good[6:], "INVALID_OPCODE"),
        (lambda good, unknown: b"\x00\x01" + good[2:], "VALIDATION_ERROR"),
        (lambda good, unknown: good[:-1], "FORMAT_ERROR"),
    ],
    ids=["unknown-opcode", "not-a-command", "short-arguments"],
)
def test_a_rejected_packet_gets_f_prime_s_response_by_name_and_the_gnc_runs_as_untouched(
    booted: ModuleType,
    station: FprimeStation,
    configuration: str,
    dictionary: Dictionary,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    change: Callable[[bytes, int], bytes],
    response: str,
    prm: str,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
    wire: Callable[..., Callable[..., int]],
):
    """F´ answers a bad packet with its `Fw.CmdResponse`, named, with no reason, and runs nothing.

    The GNC instances write on the step what a copy with no packet writes on the same step.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        station: the station on it.
        configuration: the copy's configuration.
        dictionary: its dictionary.
        decoded: drains a station's telemetry as values.
        change: makes the bad packet from a good `cmdDisp.CMD_TEST_CMD_1` and an unknown opcode.
        response: the response F´ gives it.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
        wire: wires the copy to the bus.
    """
    untouched = power_cycle(configuration)
    untouched.boot(prm, parameter_ids)
    wire(untouched, configuration, bus)(NS)
    expected = _gnc_writes(decoded(FprimeStation(untouched, dictionary)), configuration)
    assert expected

    booted.uplink(change(_test_command(dictionary), _unknown_opcode(configuration)), 7)
    wire(booted, configuration, bus)(NS)

    assert station.responses() == [(7, response, None)]
    assert _gnc_writes(decoded(station), configuration) == expected
