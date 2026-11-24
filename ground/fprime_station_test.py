"""The F´ ground station: names to command packets, and telemetry bytes to values.

The codec runs against a mock component's dictionary, generated from FPP alone. The packets that
reach the deployment crafted or malformed are made from F´'s own `cmdDisp.CMD_TEST_CMD_1`, which
every deployment has; they need the deployment `just fsw` builds, and skip without it. What every
build decodes alike is `radio_edge_test.py`'s; this file holds the station's packet layout and its
refusals.
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
from ground.conftest import NS, TlmPacker
from ground.fprime_station import FprimeStation
from lab import dictionary_path
from lab.power_cycle import power_cycle

TEST_COMMAND = "cmdDisp.CMD_TEST_CMD_1"
"""F´'s CommandDispatcher's test command, which takes arguments, in every deployment."""

GAIN = "mock.gain"
"""A channel of the mock whose value is an F32."""


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


class TestStationCodec:
    """The station on the mock's dictionary, and the packets it packs and reads."""

    @pytest.fixture(autouse=True)
    def _station(self, mock_dictionary: Dictionary) -> None:
        """Holds the mock's dictionary, a station on no deployment, and a packer on the dictionary.

        Args:
            mock_dictionary: the mock's dictionary.
        """
        self.dictionary = mock_dictionary
        self.station = FprimeStation(ModuleType("no_deployment"), mock_dictionary)
        self.packer = TlmPacker(mock_dictionary)

    def test_a_command_packet_is_f_prime_s(self):
        """Descriptor, opcode, then big-endian arguments; an F32 is truncated and a bool is 0xFF."""
        packet = self.station.encode_command("mock.setMock", self.dictionary.arguments("mock.setMock", ARGS))

        assert packet[:6] == struct.pack(">HI", 0, 0x1000), "the descriptor and opcode lead"
        assert packet[6:10] == struct.pack(">f", 0.1), "an F32 is four bytes"
        assert packet[10] == 0xFF, "a true bool is 0xFF"
        assert packet[11:15] == struct.pack(">i", 1), "an enum is its number"
        assert packet[15:39] == struct.pack(">3d", 1.0, 2.0, 3.0), "an array is its elements"
        assert packet[39:111] == struct.pack(">9d", *range(9)), "a matrix is its elements row by row"
        assert packet[111:] == bytes([7]), "a U8 is one byte, last"

    @pytest.mark.parametrize(
        ("name", "args", "error", "match"),
        [
            ("mock.setMock", {k: v for k, v in ARGS.items() if k != "mode"}, KeyError, "'mode'"),
            ("mock.label", {"note": "hello"}, ValueError, r"mock\.label has a parameter type"),
        ],
        ids=["missing-argument", "type-not-coded"],
    )
    def test_a_command_the_station_cannot_encode_is_refused_naming_what(
        self, name: str, args: dict, error: type[BaseException], match: str
    ):
        """A missing argument, or a parameter of a type not coded, raises naming it.

        Args:
            name: the command encoded.
            args: its arguments.
            error: what encoding raises.
            match: what the error names.
        """
        with pytest.raises(error, match=match):
            self.station.encode_command(name, args)

    def test_telemetry_packets_become_each_channel_s_tags_and_values_in_one_batch(self):
        """Arrays come back (N, *shape), an enum as its name, an F32 as F32 holds it.

        The channels' sizes differ, so each entry's length is the channel's, and a channel's entries
        in two packets come back in the order downlinked.
        """
        first = self.packer.packet(
            [
                (GAIN, 10_500_000_000, 0.1),
                ("mock.offset", 10_500_000_000, [1, 2, 3]),
                ("mock.mode", 10_500_001_000, 1),
            ],
        )
        second = self.packer.packet(
            [("mock.offset", 11 * NS, [4, 5, 6]), ("mock.mounting", 11 * NS, np.arange(9.0).reshape(3, 3))],
        )

        decoded = self.station.decode([self.packer.downlink([first, second])])

        assert set(decoded) == {GAIN, "mock.offset", "mock.mode", "mock.mounting"}, "every channel written is decoded"
        assert decoded["mock.offset"].times.tolist() == [10_500_000_000, 11 * NS], "a channel's tags follow its packets"
        np.testing.assert_array_equal(
            decoded["mock.offset"].values, [[1, 2, 3], [4, 5, 6]], err_msg="an array channel is (N, *shape)"
        )
        assert decoded["mock.mode"].times.tolist() == [10_500_001_000], "a microsecond is kept"
        assert decoded["mock.mode"].values.tolist() == ["fast"], "an enum comes back as its name"
        assert decoded[GAIN].values.tolist() == [float(np.float32(0.1))], "an F32 comes back as F32 holds it"
        np.testing.assert_array_equal(
            decoded["mock.mounting"].values, [np.arange(9.0).reshape(3, 3)], err_msg="a matrix keeps its shape"
        )

    def test_a_channel_written_twice_across_packets_keeps_every_value_in_order(self):
        """Two entries of one channel in one packet and a third in the next all come back in order."""
        first = self.packer.packet([(GAIN, NS, 0.5), (GAIN, NS, 0.25)])
        second = self.packer.packet([(GAIN, NS, 0.125)])

        writes = self.station.decode([self.packer.downlink([first, second])])[GAIN]

        assert writes.times.tolist() == [NS] * 3, "no entry is dropped for sharing a tag"
        assert writes.values.tolist() == [0.5, 0.25, 0.125], "the entries keep the order downlinked"

    @pytest.mark.parametrize("descriptor", ["FW_PACKET_LOG", "FW_PACKET_COMMAND", "FW_PACKET_FILE"])
    def test_a_downlinked_packet_that_is_not_telemetry_is_refused(self, descriptor: str):
        """A packet whose descriptor is not `FW_PACKET_TELEM` raises `ValueError` saying so.

        The packet is the second of two, so the message names index 1.

        Args:
            descriptor: the `ComCfg.Apid` constant the bad packet holds.
        """
        good = self.packer.packet([(GAIN, NS, 0.5)])
        bad = self.packer.packet([(GAIN, NS, 0.5)], descriptor)

        with pytest.raises(ValueError, match=rf"downlinked packet 1 is {descriptor}, not FW_PACKET_TELEM"):
            self.station.decode([self.packer.downlink([good, bad])])

    def test_a_packet_whose_descriptor_is_no_apid_constant_is_refused_naming_its_number(self):
        """A descriptor that no `ComCfg.Apid` constant has raises `ValueError` naming the number."""
        constants = self.dictionary.type("ComCfg.Apid").constants
        assert constants is not None, "`ComCfg.Apid` is an enum"
        number = max(constants.values()) + 1
        good = self.packer.packet([(GAIN, NS, 0.5)])
        bad = self.packer.packet([(GAIN, NS, 0.5)], number)

        with pytest.raises(ValueError, match=rf"downlinked packet 1 is {number}, not FW_PACKET_TELEM"):
            self.station.decode([self.packer.downlink([good, bad])])

    def test_a_telemetry_packet_holding_no_entry_decodes_to_nothing_alone_and_among_good_packets(self):
        """A descriptor with no entry after it adds no value, and leaves the packets around it intact."""
        empty = self.packer.packet([])
        first = self.packer.packet([(GAIN, NS, 0.5)])
        last = self.packer.packet([(GAIN, 2 * NS, 0.25)])

        alone = self.station.decode([self.packer.downlink([empty])])
        among = self.station.decode([self.packer.downlink([first, empty, last])])

        assert alone == {}, "a packet of no entry decodes to no channel"
        assert list(among) == [GAIN], "the packets around it decode"
        assert among[GAIN].times.tolist() == [NS, 2 * NS], "both neighbours' tags are kept"
        assert among[GAIN].values.tolist() == [0.5, 0.25], "both neighbours' values are kept"

    @pytest.mark.parametrize("above", [True, False], ids=["above-every-id", "below-every-id"])
    def test_an_entry_of_a_channel_the_dictionary_lacks_is_refused_naming_its_id(self, above: bool):
        """A channel ID not in the dictionary raises `ValueError` rather than misreading later entries.

        The ID lies beyond the largest ID or short of the smallest, which the search for it finds by
        different routes.

        Args:
            above: whether the ID is above every ID the dictionary holds, or below.
        """
        ids = [channel.id for channel in self.dictionary.channels_by_id.values()]
        assert min(ids) > 0, "an ID below the smallest exists only while the smallest is above 0"
        unknown_id = max(ids) + 1 if above else min(ids) - 1
        good = self.packer.packet([(GAIN, NS, 0.5)])
        unknown = self.packer.with_channel_id(good, unknown_id)

        with pytest.raises(
            ValueError, match=rf"downlinked packet 1 holds channel ID {unknown_id:#x}, not in the dictionary"
        ):
            self.station.decode([self.packer.downlink([good, unknown])])

    def test_a_downlink_whose_packet_sizes_disagree_with_its_bytes_is_refused(self):
        """Sizes summing to other than the byte count raise `ValueError` naming both."""
        packet = self.packer.packet([(GAIN, NS, 0.5)])
        sizes = np.array([len(packet) + 3], np.uint32).tobytes()

        with pytest.raises(ValueError, match=rf"packet sizes sum to {len(packet) + 3} bytes, not its {len(packet)}"):
            self.station.decode([(packet, sizes)])

    @pytest.mark.parametrize(
        "length",
        [
            lambda empty, one, two: empty - 1,
            lambda empty, one, two: empty + 1,
            lambda empty, one, two: two - 4,
            lambda empty, one, two: two - 1,
            lambda empty, one, two: one + 1,
        ],
        ids=[
            "inside-the-descriptor",
            "inside-the-first-channel-id",
            "second-entry-overruns-by-a-field",
            "second-entry-overruns-by-a-byte",
            "inside-the-second-channel-id",
        ],
    )
    def test_a_packet_cut_short_is_refused_naming_its_index(self, length: Callable[[int, int, int], int]):
        """A packet cut inside its descriptor, a channel ID, or an entry's value raises `ValueError`.

        The packet holds two entries and is the second of two, so the message names index 1.

        Args:
            length: the length to cut to, from the sizes of a packet of no entry, one and two.
        """
        entries = [(GAIN, NS, 0.5), (GAIN, NS, 0.25)]
        good = self.packer.packet(entries[:1])
        two = self.packer.packet(entries)
        sizes = (len(self.packer.packet([])), len(good), len(two))

        with pytest.raises(ValueError, match=r"downlinked packet 1 is cut short"):
            self.station.decode([self.packer.downlink([good, two[: length(*sizes)]])])

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
        self,
        booted: ModuleType,
        station: FprimeStation,
        configuration: str,
        dictionary: Dictionary,
        decoded: Callable[[Any], list[tuple[str, int, Any]]],
        change: Callable[[bytes, int], bytes],
        response: str,
        prm: str,
        boot_idle: Callable[..., None],
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
            boot_idle: boots a copy on its parameter file.
            bus: every role's bus message on its LabBusDriver port.
            wire: wires the copy to the bus.
        """
        untouched = power_cycle(configuration)
        boot_idle(untouched, prm)
        wire(untouched, configuration, bus)(NS)
        expected = _gnc_writes(decoded(FprimeStation(untouched, dictionary)), configuration)
        assert expected, "a copy with no packet writes GNC telemetry on its step"

        booted.uplink(change(_test_command(dictionary), _unknown_opcode(configuration)), 7)
        wire(booted, configuration, bus)(NS)

        assert station.responses() == [(7, response, None)], "F´ answers the bad packet by name, with no reason"
        assert _gnc_writes(decoded(station), configuration) == expected, "the GNC runs as if untouched"
