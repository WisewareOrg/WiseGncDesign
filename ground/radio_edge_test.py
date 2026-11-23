"""What every radio edge decodes alike: the Python build's and the F´ build's.

Both are held to one dictionary from FPP alone, the `MockFrame` sub-topology's, so neither needs the
F´ build. Each test feeds a build the writes in its own downlink form and reads back what the
ground reads.
"""

import json
from pathlib import Path
from types import ModuleType
from typing import Protocol

import numpy as np
import pytest

from fsw.mock import MOCK
from fsw.mock.mock_gnc import Sink, Source
from fsw.python import FrameRunner
from ground.conftest import NS, TlmPacker, Write
from ground.fprime_station import FprimeStation
from ground.radio_edge import RadioEdge

LEVEL = "source.level"
"""An F64 channel of the mock."""

RECEIVED = "sink.received"
"""Another F64 channel of the mock, whose name sorts before `LEVEL`'s."""


class Build(Protocol):
    """A radio edge and the downlink it decodes, made from writes.

    Attributes:
        edge: the radio edge.
    """

    edge: RadioEdge

    def downlink(self, writes: list[Write]) -> object:
        """The raw downlink the build gives for those writes, in one drain.

        Args:
            writes: `(channel, time tag in ns, value)`, in write order.

        Returns:
            What the edge's `decode` takes as one drain.
        """
        ...


class PythonBuild:
    """The Python build: a drain is one entry per write.

    Attributes:
        edge: the frame runner.
    """

    def __init__(self, edge: FrameRunner) -> None:
        """Holds the frame runner.

        Args:
            edge: the frame runner.
        """
        self.edge = edge

    def downlink(self, writes: list[Write]) -> object:
        """One entry per write.

        Args:
            writes: `(channel, time tag in ns, value)`, in write order.

        Returns:
            The entries.
        """
        return [((name,), t_ns, (value,)) for name, t_ns, value in writes]


class FprimeBuild:
    """The F´ build: a drain is one `TlmPacket` of the writes.

    Attributes:
        edge: the station.
    """

    def __init__(self, edge: FprimeStation) -> None:
        """Holds the station and a packer on its dictionary.

        Args:
            edge: the station, on no deployment.
        """
        self.edge = edge
        self._packer = TlmPacker(edge.dictionary)

    def downlink(self, writes: list[Write]) -> object:
        """One packet of the writes; none for no write.

        Args:
            writes: `(channel, time tag in ns, value)`, in write order.

        Returns:
            The packets and their sizes.
        """
        return self._packer.downlink([self._packer.packet(writes)] if writes else [])


@pytest.fixture(params=["python", "fprime"])
def build(request: pytest.FixtureRequest, tmp_path: Path) -> Build:
    """Each build in turn, on the `MockFrame` dictionary.

    Args:
        request: the build's name.
        tmp_path: where the Python build's record is written.

    Returns:
        The build.
    """
    record = tmp_path / "run_0000.prm.json"
    record.write_text(json.dumps({"MockFrame.source": {"gain": 2.5}, "MockFrame.sink": {"offset": 0.25}}))
    runner = FrameRunner("MockFrame", record, (Source, Sink), contract=MOCK)
    if request.param == "python":
        return PythonBuild(runner)
    return FprimeBuild(FprimeStation(ModuleType("no_deployment"), runner.dictionary))


class TestDecodeContract:
    """What `decode` gives, whichever build's downlink it reads."""

    @pytest.fixture(autouse=True)
    def _build(self, build: Build) -> None:
        """Holds the build under test.

        Args:
            build: the build.
        """
        self.build = build

    def test_every_write_comes_back_with_its_int64_tag_and_value(self):
        """A channel's writes come back as int64 ns tags and values, one row per write."""
        drain = self.build.downlink([(LEVEL, 2 * NS, 1.5), (RECEIVED, 3 * NS, 4.0)])

        decoded = self.build.edge.decode([drain])

        assert set(decoded) == {LEVEL, RECEIVED}, "each channel written is decoded, and no other"
        assert decoded[LEVEL].times.dtype == np.int64, "time tags are int64"
        assert decoded[LEVEL].times.tolist() == [2 * NS], "the tag is the write's, in ns"
        assert decoded[LEVEL].values.tolist() == [1.5], "the value is the write's"
        assert decoded[RECEIVED].times.tolist() == [3 * NS], "another channel keeps its own tag"
        assert decoded[RECEIVED].values.tolist() == [4.0], "another channel keeps its own value"

    def test_a_channel_written_twice_with_one_tag_keeps_both_values_in_order(self):
        """Two writes of one channel at one tag both come back, in the order written."""
        drain = self.build.downlink([(LEVEL, NS, 0.5), (LEVEL, NS, 0.25), (LEVEL, NS, 0.125)])

        writes = self.build.edge.decode([drain])[LEVEL]

        assert writes.times.tolist() == [NS] * 3, "no write is dropped for sharing a tag"
        assert writes.values.tolist() == [0.5, 0.25, 0.125], "the writes keep the order written"

    def test_names_keeps_those_channels_and_no_other(self):
        """`names` keeps the channels named, whatever their place in the drain."""
        drain = self.build.downlink([(LEVEL, NS, 1.0), (RECEIVED, NS, 2.0)])

        decoded = self.build.edge.decode([drain], [RECEIVED])

        assert list(decoded) == [RECEIVED], "only the named channel is decoded"
        assert decoded[RECEIVED].values.tolist() == [2.0], "the named channel keeps its value"

    def test_several_drains_decode_together_oldest_first(self):
        """A channel's writes across drains come back in the order the drains are given."""
        first = self.build.downlink([(LEVEL, NS, 1.0)])
        second = self.build.downlink([(LEVEL, 2 * NS, 2.0)])

        writes = self.build.edge.decode([first, second])[LEVEL]

        assert writes.times.tolist() == [NS, 2 * NS], "the older drain's tag comes first"
        assert writes.values.tolist() == [1.0, 2.0], "the older drain's value comes first"

    def test_an_empty_drain_adds_nothing_and_no_drain_decodes_to_nothing(self):
        """An empty drain among others adds no write; only empty drains, or none, give `{}`."""
        empty = self.build.downlink([])
        full = self.build.downlink([(LEVEL, NS, 1.0)])

        among = self.build.edge.decode([empty, full, empty])

        assert among[LEVEL].values.tolist() == [1.0], "empty drains leave the writes around them"
        assert self.build.edge.decode([empty, empty]) == {}, "empty drains decode to no channel"
        assert self.build.edge.decode([]) == {}, "no drain decodes to no channel"

    def test_the_channels_are_keyed_in_the_order_of_their_first_write_across_drains(self):
        """Channels whose names sort opposite to their first writes are keyed by first write."""
        first = self.build.downlink([(LEVEL, NS, 1.0)])
        second = self.build.downlink([(RECEIVED, 2 * NS, 2.0), (LEVEL, 2 * NS, 3.0)])

        assert list(self.build.edge.decode([first, second])) == [LEVEL, RECEIVED], "oldest first write first"
        assert list(self.build.edge.decode([second, first])) == [RECEIVED, LEVEL], "the drains' order decides it"
