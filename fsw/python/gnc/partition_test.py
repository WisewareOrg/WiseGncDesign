"""The Python build's GNC partition runs a sub-topology's algorithms as its FPP wires them.

A mock sub-topology of three components on two rate groups, read from a temporary `.fpp` with the
contract, flown with stub classes that log each step. The CDH writes its input `seedIn`, and reads
its output `slowOut`.
"""

from collections import namedtuple
from pathlib import Path
from typing import Any

import pytest

from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import Model, read
from fsw.mock import edited
from fsw.python.gnc.partition import Frame, GncPartition
from fsw.python.platform.rates import RateGroupDriver, dividers

MOCK = """\
module Mock {

  constant fastDivider = 1
  constant slowDivider = 2

  struct Value {
    x: F64
  }

  port Value(value: Value)

  passive component Source {
    sync input port schedIn: Svc.Sched
    sync input port seedIn: Value
    output port valueOut: Value
    output port echoOut: Value
  }

  passive component Sink {
    sync input port schedIn: Svc.Sched
    sync input port valueIn: Value
  }

  passive component Slow {
    sync input port schedIn: Svc.Sched
    sync input port valueIn: Value
    output port slowOut: Value
  }

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x400
  instance fastRateGroup: Svc.PassiveRateGroup base id 0x1100
  instance slowRateGroup: Svc.PassiveRateGroup base id 0x1200
  instance sink: Sink base id 0x2000
  instance slow: Slow base id 0x2100
  instance source: Source base id 0x2200

  topology Gnc {

    instance rateGroupDriver
    instance fastRateGroup
    instance slowRateGroup
    instance sink
    instance slow
    instance source

    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> fastRateGroup.CycleIn
      rateGroupDriver.CycleOut[1] -> slowRateGroup.CycleIn
      fastRateGroup.RateGroupMemberOut[0] -> source.schedIn
      fastRateGroup.RateGroupMemberOut[1] -> sink.schedIn
      slowRateGroup.RateGroupMemberOut[0] -> slow.schedIn
    }

    connections Data {
      source.valueOut -> sink.valueIn
      source.echoOut -> slow.valueIn
    }

    port tickIn = rateGroupDriver.CycleIn
    port seedIn = source.seedIn
    port slowOut = slow.slowOut

  }

}
"""

Value = namedtuple("Value", ["x"])
"""The mock's `Mock.Value`."""

SourceOutputs = namedtuple("SourceOutputs", ["valueOut", "echoOut"], defaults=[None, None])
"""The source's outputs; `echoOut` is written on odd seeds only."""

SourceTelemetry = namedtuple("SourceTelemetry", ["count"], defaults=[None])
"""The source's telemetry."""

SlowOutputs = namedtuple("SlowOutputs", ["slowOut"], defaults=[None])
"""Slow's outputs; `slowOut` is written for an echo above 2 only."""

Nothing = namedtuple("Nothing", [])
"""A component's empty outputs or telemetry."""

LOG: list[tuple] = []
"""Each step, as `(instance, t, input)`, in the order run."""


class Source:
    """Doubles its seed onto `valueOut`, and echoes an odd seed onto `echoOut`."""

    def __init__(self, parameters: object) -> None:
        """Keeps its parameters.

        Args:
            parameters: whatever boot gave it.
        """
        self.parameters = parameters

    def step(self, t: float, seed: Value) -> tuple[SourceOutputs, SourceTelemetry]:
        """Logs the step.

        Args:
            t: s, the time.
            seed: the seed.

        Returns:
            Its outputs and its telemetry.
        """
        LOG.append(("source", t, seed))
        echo = seed if seed.x % 2 else None
        return SourceOutputs(valueOut=Value(2 * seed.x), echoOut=echo), SourceTelemetry(count=1)


class Sink:
    """Takes the source's value."""

    def __init__(self, parameters: object) -> None:
        """Keeps nothing.

        Args:
            parameters: whatever boot gave it.
        """

    def step(self, t: float, value: Value) -> tuple[Any, Any]:
        """Logs the step.

        Args:
            t: s, the time.
            value: the source's value.

        Returns:
            Nothing written.
        """
        LOG.append(("sink", t, value))
        return Nothing(), Nothing()


class Slow(Sink):
    """Takes the source's echo, at half the rate, and sends an echo above 2 out of the GNC."""

    def step(self, t: float, value: Value) -> tuple[SlowOutputs, Nothing]:
        """Logs the step.

        Args:
            t: s, the time.
            value: the source's latest echo.

        Returns:
            The echo on `slowOut` when above 2, else nothing, and no telemetry.
        """
        LOG.append(("slow", t, value))
        return SlowOutputs(slowOut=value if value.x > 2 else None), Nothing()


def _model(directory: Path, mock: str = MOCK) -> Model:
    """The mock sub-topology's model, read with the contract.

    Args:
        directory: where `Mock.fpp` is written.
        mock: the mock's FPP.

    Returns:
        The model.
    """
    (directory / "Mock.fpp").write_text(mock)
    return read([*contract_files(), directory / "Mock.fpp"])


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> Model:
    """The mock's model, read once.

    Args:
        tmp_path_factory: where the mock is written.

    Returns:
        The model.
    """
    return _model(tmp_path_factory.mktemp("mock"))


@pytest.fixture
def gnc(model: Model) -> GncPartition:
    """The mock's partition, booted, with the log cleared.

    Args:
        model: the mock's model.

    Returns:
        The partition.
    """
    LOG.clear()
    partition = GncPartition(model, "Mock", (Sink, Slow, Source))
    partition.boot({"source": "p", "sink": None, "slow": None})
    return partition


def test_members_run_in_rate_group_order_and_an_output_reaches_a_later_member_in_its_frame(
    gnc: GncPartition,
):
    """Source runs before sink, as `RateGroupMemberOut` numbers them, and sink gets its value.

    Declared and sorted by name, sink would come first; the wiring, not the name, orders them. The
    CDH writes every sub-topology input port but the driver's `tickIn`, and reads every output port.

    Args:
        gnc: the mock's partition.
    """
    gnc.write("seedIn", Value(3.0))

    telemetry = gnc.run(1.0, [0]).telemetry

    assert [("source", 1.0, Value(3.0)), ("sink", 1.0, Value(6.0))] == LOG
    assert telemetry == [("source", SourceTelemetry(count=1)), ("sink", Nothing())]


def test_a_rebooted_partition_routes_its_new_algorithms_outputs(gnc: GncPartition):
    """After a second boot, a written input and a routed output reach the algorithms that boot built.

    Args:
        gnc: the mock's partition.
    """
    gnc.write("seedIn", Value(3.0))
    gnc.run(1.0, [0])
    gnc.boot({"source": "p", "sink": None, "slow": None})
    LOG.clear()

    gnc.write("seedIn", Value(5.0))
    gnc.run(2.0, [0])

    assert [("source", 2.0, Value(5.0)), ("sink", 2.0, Value(10.0))] == LOG


def test_frames_follow_the_fpp_rate_constants_and_return_the_outputs_their_members_wrote(
    gnc: GncPartition, model: Model
):
    """Slow's group, `slowDivider` = 2, runs at the first tick and every second one after.

    An unwritten output, the echo of an even seed, leaves slow's input at the last echo. A frame
    returns `slowOut` only when slow ran and wrote it: it writes an echo above 2 only, so the first
    run's echo of 1 writes nothing.

    Args:
        gnc: the mock's partition.
        model: the mock's model.
    """
    driver = RateGroupDriver(dividers(model, gnc.rate_groups))
    assert gnc.rate_groups == ("Mock.fastRateGroup", "Mock.slowRateGroup")
    outputs = []
    for t, seed in ((1.0, 1.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0)):
        gnc.write("seedIn", Value(seed))
        frame = gnc.run(t, driver.tick())
        assert isinstance(frame, Frame)
        outputs.append(frame.outputs)

    assert outputs == [{}, {}, {"slowOut": Value(3.0)}, {}, {"slowOut": Value(5.0)}]
    assert [(t, value) for name, t, value in LOG if name == "slow"] == [
        (1.0, Value(1.0)),
        (3.0, Value(3.0)),
        (5.0, Value(5.0)),
    ]
    assert [t for name, t, _ in LOG if name == "source"] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_a_step_whose_input_was_never_written_raises_naming_the_port(gnc: GncPartition):
    """No input has a default: the source's seed was never written.

    Args:
        gnc: the mock's partition.
    """
    with pytest.raises(RuntimeError, match=r"source\.seedIn"):
        gnc.run(1.0, [0])


def test_boot_drops_every_input_held(gnc: GncPartition):
    """A power cycle leaves no input written: the seed written before boot is gone after it.

    Args:
        gnc: the mock's partition.
    """
    gnc.write("seedIn", Value(3.0))

    gnc.boot({"source": "p", "sink": None, "slow": None})

    with pytest.raises(RuntimeError, match=r"source\.seedIn"):
        gnc.run(1.0, [0])


@pytest.mark.parametrize(
    ("classes", "named"),
    [
        ((Sink, Source), r"no class for the components \['Slow'\]; the classes \[\] match"),
        ((Sink, Slow, Source, Value), r"no class for the components \[\]; the classes \['Value'\]"),
    ],
    ids=["missing", "extra"],
)
def test_a_class_missing_for_a_component_or_matching_none_is_refused_naming_it(
    model: Model, classes: tuple[type, ...], named: str
):
    """Each member's component needs its class, matched by name, and every class a member.

    Args:
        model: the mock's model.
        classes: the classes given.
        named: the error, naming the class missing or the class matching no member.
    """
    with pytest.raises(ValueError, match=named):
        GncPartition(model, "Mock", classes)


@pytest.mark.parametrize(
    ("edits", "match"),
    [
        (
            (("    port slowOut = slow.slowOut\n", "    port echoOut = source.echoOut\n"),),
            r"source\.echoOut .*port echoOut",
        ),
        (
            (
                (
                    "    sync input port valueIn: Value\n  }\n\n  passive component Slow",
                    "    sync input port value: Value\n  }\n\n  passive component Slow",
                ),
                ("source.valueOut -> sink.valueIn", "source.valueOut -> sink.value"),
            ),
            r"sink\.value\b",
        ),
        (
            (
                (
                    "    sync input port valueIn: Value\n  }\n\n  passive component Slow",
                    "    sync input port valueIn: Value\n    sync input port backIn: Value\n  }\n\n"
                    "  passive component Slow",
                ),
                (
                    "    output port slowOut: Value\n  }\n\n  instance",
                    "    output port slowOut: Value\n    output port backOut: Value\n  }\n\n  instance",
                ),
                (
                    "      source.echoOut -> slow.valueIn\n",
                    "      source.echoOut -> slow.valueIn\n      slow.backOut -> sink.backIn\n",
                ),
            ),
            r"slow\.backOut -> sink\.backIn is a backward edge",
        ),
        (
            (
                (
                    "    output port echoOut: Value\n",
                    "    output port echoOut: Value\n    output port loopOut: Value\n"
                    "    sync input port loopIn: Value\n",
                ),
                (
                    "      source.echoOut -> slow.valueIn\n",
                    "      source.echoOut -> slow.valueIn\n      source.loopOut -> source.loopIn\n",
                ),
            ),
            r"source\.loopOut -> source\.loopIn is a backward edge",
        ),
        (
            (
                ("    output port valueOut: Value\n", "    output port valueOut: [2] Value\n"),
                (
                    "      source.valueOut -> sink.valueIn\n",
                    "      source.valueOut[0] -> sink.valueIn\n      source.valueOut[1] -> slow.doubleIn\n",
                ),
                (
                    "    output port slowOut: Value\n  }\n\n  instance",
                    "    output port slowOut: Value\n    sync input port doubleIn: Value\n  }\n\n  instance",
                ),
            ),
            r"source\.valueOut routes to more than one input",
        ),
    ],
    ids=["routed-and-exposed", "input-not-named-in", "backward-edge", "self-loop", "fan-out"],
)
def test_a_partition_the_frame_cannot_run_is_refused_naming_the_edge(
    tmp_path: Path, edits: tuple[tuple[str, str], ...], match: str
):
    """An output feeds one input or one port; a data input is `<name>In`; no edge runs backward.

    A connected input's keyword is its name without `In`, so another name has none. An edge into a
    member that runs earlier in the frame, or from a member to itself, is a delayed feedback, not
    supported. FPP fans one output out only through a port array; the partition refuses it.

    Args:
        tmp_path: where the mock is written.
        edits: the mock's edits.
        match: the refusal, naming what breaks.
    """
    with pytest.raises(ValueError, match=match):
        GncPartition(_model(tmp_path, edited(MOCK, *edits)), "Mock", (Sink, Slow, Source))
