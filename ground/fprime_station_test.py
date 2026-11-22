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
    mock: FprimeStation, name: str, args: dict, error: type, match: str
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


def test_serialized_writes_become_values_in_one_batch(mock: FprimeStation):
    """Arrays come back (N, *shape), an enum as its name, an F32 as F32 holds it.

    Args:
        mock: the mock's station.
    """
    np.testing.assert_array_equal(
        mock.values("mock.offset", [struct.pack(">3d", 1, 2, 3), struct.pack(">3d", 4, 5, 6)]),
        [[1, 2, 3], [4, 5, 6]],
    )
    assert mock.values("mock.mode", [struct.pack(">i", 1)]).tolist() == ["fast"]
    assert mock.values("mock.gain", [struct.pack(">f", 0.1)]).tolist() == [float(np.float32(0.1))]


@pytest.mark.parametrize(
    ("channel", "serialized"),
    [
        ("mock.gain", [0.5]),
        ("mock.offset", [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]),
        ("mock.offset", [struct.pack(">2d", 1.0, 2.0)]),
        ("mock.offset", [struct.pack(">2d", 1.0, 2.0), struct.pack(">4d", 3.0, 4.0, 5.0, 6.0)]),
    ],
    ids=["number", "numpy-array", "wrong-length", "misaligned"],
)
def test_values_takes_whole_serialized_values_only(
    mock: FprimeStation, channel: str, serialized: list
):
    """Written values, numpy arrays included, or bytes of the wrong length fail, naming the channel.

    Args:
        mock: the mock's station.
        channel: the channel decoded.
        serialized: what is handed to `values`.
    """
    with pytest.raises(ValueError, match=rf"channel {channel} "):
        mock.values(channel, serialized)


def _test_command(dictionary: Dictionary) -> bytes:
    """`cmdDisp.CMD_TEST_CMD_1` with an argument of each parameter's type, as the station codes it.

    Args:
        dictionary: the deployment's dictionary.

    Returns:
        The packet.
    """
    command = dictionary.command(TEST_COMMAND)
    args = {
        param: 1.5 if type_.dtype.kind == "f" else 1
        for param, type_ in zip(command.params, command.types, strict=True)
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


def _gnc_writes(
    writes: list[tuple[str, int, Any]], configuration: str
) -> list[tuple[str, int, Any]]:
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
    """
    untouched = power_cycle(configuration)
    untouched.boot(prm, parameter_ids)
    untouched.step(t_ns=NS, bus=bus)
    expected = _gnc_writes(decoded(FprimeStation(untouched, dictionary)), configuration)
    assert expected

    booted.uplink(change(_test_command(dictionary), _unknown_opcode(configuration)), 7)
    booted.step(t_ns=NS, bus=bus)

    assert station.responses() == [(7, response, None)]
    assert _gnc_writes(decoded(station), configuration) == expected
