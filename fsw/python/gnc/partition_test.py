"""The Python build's GNC partition runs a sub-topology's algorithms as its FPP wires them.

A toy sub-topology of three components on two rate groups, read from a temporary `.fpp` with the
contract, flown with stub classes that log each step.
"""

from collections import namedtuple
from pathlib import Path

import pytest

from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import Model, read
from fsw.python.gnc.partition import GncPartition
from fsw.python.platform.rates import RateGroupDriver, dividers

TOY = """\
module Toy {

  @ s, the base tick's period
  constant tickPeriod = 1.0
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

  }

}
"""

Value = namedtuple("Value", ["x"])
"""The toy's `Toy.Value`."""

SourceOutputs = namedtuple("SourceOutputs", ["valueOut", "echoOut"], defaults=[None, None])
"""The source's outputs; `echoOut` is written on odd seeds only."""

SourceTelemetry = namedtuple("SourceTelemetry", ["count"], defaults=[None])
"""The source's telemetry."""

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

    def step(self, t: float, value: Value) -> tuple[Nothing, Nothing]:
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
    """Takes the source's echo, at half the rate."""

    def step(self, t: float, value: Value) -> tuple[Nothing, Nothing]:
        """Logs the step.

        Args:
            t: s, the time.
            value: the source's latest echo.

        Returns:
            Nothing written.
        """
        LOG.append(("slow", t, value))
        return Nothing(), Nothing()


def _model(directory: Path, toy: str = TOY) -> Model:
    """The toy sub-topology's model, read with the contract.

    Args:
        directory: where `Toy.fpp` is written.
        toy: the toy's FPP.

    Returns:
        The model.
    """
    (directory / "Toy.fpp").write_text(toy)
    return read([*contract_files(), directory / "Toy.fpp"])


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> Model:
    """The toy's model, read once.

    Args:
        tmp_path_factory: where the toy is written.

    Returns:
        The model.
    """
    return _model(tmp_path_factory.mktemp("toy"))


@pytest.fixture
def gnc(model: Model) -> GncPartition:
    """The toy's partition, booted, with the log cleared.

    Args:
        model: the toy's model.

    Returns:
        The partition.
    """
    LOG.clear()
    partition = GncPartition(model, "Toy", (Sink, Slow, Source))
    partition.boot({"source": "p", "sink": None, "slow": None})
    return partition


def test_members_run_in_rate_group_order_and_an_output_reaches_a_later_member_in_its_frame(
    gnc: GncPartition,
):
    """Source runs before sink, as `RateGroupMemberOut` numbers them, and sink gets its value.

    Declared and sorted by name, sink would come first; the wiring, not the name, orders them.

    Args:
        gnc: the toy's partition.
    """
    gnc.write("seedIn", Value(3.0))

    telemetry = gnc.run(1.0, [0])

    assert [("source", 1.0, Value(3.0)), ("sink", 1.0, Value(6.0))] == LOG
    assert telemetry == [("source", SourceTelemetry(count=1)), ("sink", Nothing())]
    assert gnc.algorithms["source"].parameters == "p"
    assert sorted(gnc.algorithms) == ["sink", "slow", "source"]


def test_frames_follow_the_fpp_rate_constants_and_an_input_keeps_its_latest_value(
    gnc: GncPartition, model: Model
):
    """Slow's group, `slowDivider` = 2, runs at the first tick and every second one after.

    An unwritten output, the echo of an even seed, leaves slow's input at the last echo.

    Args:
        gnc: the toy's partition.
        model: the toy's model.
    """
    driver = RateGroupDriver(dividers(model, gnc.rate_groups))
    assert gnc.rate_groups == ("Toy.fastRateGroup", "Toy.slowRateGroup")
    for t, seed in ((1.0, 1.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0)):
        gnc.write("seedIn", Value(seed))
        gnc.run(t, driver.tick())

    assert [(t, value) for name, t, value in LOG if name == "slow"] == [
        (1.0, Value(1.0)),
        (3.0, Value(3.0)),
        (5.0, Value(5.0)),
    ]
    assert [t for name, t, _ in LOG if name == "source"] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_a_step_whose_input_was_never_written_raises_naming_the_port(gnc: GncPartition):
    """No input has a default: the source's seed was never written.

    Args:
        gnc: the toy's partition.
    """
    with pytest.raises(RuntimeError, match=r"source\.seedIn"):
        gnc.run(1.0, [0])


def test_boot_builds_every_algorithm_afresh(gnc: GncPartition):
    """A second boot replaces each algorithm with a new one on the parameters given.

    Args:
        gnc: the toy's partition.
    """
    first = gnc.algorithms["source"]

    gnc.boot({"source": "q", "sink": None, "slow": None})

    assert gnc.algorithms["source"] is not first
    assert gnc.algorithms["source"].parameters == "q"


@pytest.mark.parametrize(
    ("classes", "named"),
    [((Sink, Source), "Slow"), ((Sink, Slow, Source, Value), "Value")],
    ids=["missing", "extra"],
)
def test_a_class_missing_for_a_component_or_matching_none_is_refused_naming_it(
    model: Model, classes: tuple[type, ...], named: str
):
    """Each member's component needs its class, matched by name, and every class a member.

    Args:
        model: the toy's model.
        classes: the classes given.
        named: the class or component the error names.
    """
    with pytest.raises(ValueError, match=named):
        GncPartition(model, "Toy", classes)


def test_a_data_input_not_named_in_ends_is_refused_naming_it(tmp_path: Path):
    """A connected input's keyword is its name without `In`, so another name has none.

    Args:
        tmp_path: where the toy is written.
    """
    toy = TOY.replace(
        "    sync input port valueIn: Value\n  }\n\n  passive component Slow",
        "    sync input port value: Value\n  }\n\n  passive component Slow",
    ).replace("source.valueOut -> sink.valueIn", "source.valueOut -> sink.value")

    with pytest.raises(ValueError, match=r"sink\.value\b"):
        GncPartition(_model(tmp_path, toy), "Toy", (Sink, Slow, Source))


def test_a_sub_topology_without_exactly_one_rate_group_driver_is_refused(tmp_path: Path):
    """A second driver leaves the partition no one base tick.

    Args:
        tmp_path: where the toy is written.
    """
    toy = (
        TOY.replace(
            "  instance fastRateGroup:",
            "  instance otherDriver: Svc.RateGroupDriver base id 0x4400\n  instance fastRateGroup:",
        )
        .replace(
            "      rateGroupDriver.CycleOut[1] -> slowRateGroup.CycleIn\n",
            "      otherDriver.CycleOut[0] -> slowRateGroup.CycleIn\n",
        )
        .replace(
            "    instance rateGroupDriver\n",
            "    instance rateGroupDriver\n    instance otherDriver\n",
        )
    )

    with pytest.raises(ValueError, match="2 rate group drivers"):
        GncPartition(_model(tmp_path, toy), "Toy", (Sink, Slow, Source))


def test_a_rate_group_without_its_divider_constant_is_refused_naming_it(tmp_path: Path):
    """`<stem>RateGroup` runs at the constant `<stem>Divider` of its module, which must exist.

    Args:
        tmp_path: where the toy is written.
    """
    model = _model(tmp_path, TOY.replace("  constant slowDivider = 2\n", ""))
    gnc = GncPartition(model, "Toy", (Sink, Slow, Source))

    with pytest.raises(KeyError, match=r"Toy\.slowDivider"):
        dividers(model, gnc.rate_groups)
