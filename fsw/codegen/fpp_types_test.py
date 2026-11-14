"""FPP's types as named tuples, and the converters between them, on the contract and on a toy.

Needs the F´ framework clone `just _sync` fetches, not an F´ build.
"""

from pathlib import Path
from types import SimpleNamespace

import numba
import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen.deployment import CLONE
from fsw.codegen.fpp_model import read
from fsw.codegen.fpp_model_test import _TOY_FRAMEWORK
from fsw.codegen.fpp_types import Bus, Gnc, Svc, _build, converter

TOY = """\
module Toy {

  enum Mode {
    idle
    running
  }

  array Vector3 = [3] F64

  struct Reading {
    rate: Vector3
    count: U32
    mode: Mode
  }

  struct Outer {
    inner: Reading
  }

  array Rows = [2] Vector3

  struct Shapes {
    rows: Rows
    counts: [2] U16
  }

  port ReadingPort(reading: Reading)

  port Gain(value: F64)

  port Pair(a: F64, b: F64)

  passive component Spinner {
    output port readingOut: ReadingPort
    output port gainOut: Gain
    command recv port cmdIn
    command reg port cmdRegOut
    command resp port cmdResponseOut
    telemetry port tlmOut
    time get port timeCaller
    param get port prmGetOut
    param set port prmSetOut

    telemetry speed: F64
    telemetry mode: Mode

    param gain: F64 default 2.0
    param mounting: Vector3
    param startMode: Mode default Mode.running
    param count: U32
  }

}
"""


def _toy(directory: Path, toy: str = TOY) -> dict[str, SimpleNamespace]:
    """The toy's types, its component an algorithm's.

    Args:
        directory: where `Toy.fpp` is written.
        toy: the toy's FPP.

    Returns:
        The namespaces `_build` makes, by top-level module.
    """
    algorithm = directory / "Toy.fpp"
    algorithm.write_text(toy)
    framework = [CLONE / path for path in _TOY_FRAMEWORK]
    return _build(read([*framework, algorithm]), {algorithm})


@pytest.fixture(scope="module")
def toy(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """The toy's namespace, built once.

    Args:
        tmp_path_factory: where the toy is written.

    Returns:
        Module `Toy`'s namespace.
    """
    return _toy(tmp_path_factory.mktemp("toy"))["Toy"]


def _basilisk_reading() -> messaging.IMUSensorMsgPayload:
    """An IMU reading as Basilisk writes it, every field distinct.

    Returns:
        The payload.
    """
    payload = messaging.IMUSensorMsgPayload()
    payload.DVFramePlatform = [0.1, 0.2, 0.3]
    payload.AccelPlatform = [1.0, -2.0, 9.81]
    payload.DRFramePlatform = [0.01, 0.02, 0.03]
    payload.AngVelPlatform = [1e-3, -2e-3, 3e-3]
    return payload


def test_a_basilisk_reading_reaches_the_icd_through_the_bus_struct():
    """Basilisk -> `Bus.ImuSensorMsg` -> `Gnc.ImuReading` keeps the ICD fields as float64 arrays."""
    payload = _basilisk_reading()

    bus = converter(messaging.IMUSensorMsgPayload, Bus.ImuSensorMsg)(payload)
    reading = converter(Bus.ImuSensorMsg, Gnc.ImuReading)(bus)

    assert type(bus) is Bus.ImuSensorMsg
    assert np.array_equal(bus.drFramePlatform, payload.DRFramePlatform)
    assert type(reading) is Gnc.ImuReading
    assert np.array_equal(reading.angVelPlatform, payload.AngVelPlatform)
    assert np.array_equal(reading.accelPlatform, payload.AccelPlatform)
    for field in (*bus, *reading):
        assert isinstance(field, np.ndarray)
        assert field.dtype == np.dtype("float64")
    assert reading.angVelPlatform is not bus.angVelPlatform


def test_a_converter_missing_a_target_field_in_its_source_fails_naming_it():
    """The ICD has no `dvFramePlatform`, so no converter from it to the bus struct is built."""
    with pytest.raises(ValueError, match="dvFramePlatform"):
        converter(Gnc.ImuReading, Bus.ImuSensorMsg)


def test_a_misspelt_field_raises():
    """A misspelt field fails building the tuple and reading it."""
    vector = np.zeros(3)
    with pytest.raises(TypeError, match="angVelPlatfrom"):
        Gnc.ImuReading(angVelPlatfrom=vector, accelPlatform=vector)

    reading = Gnc.ImuReading(angVelPlatform=vector, accelPlatform=vector)
    with pytest.raises(AttributeError):
        reading.angvelplatform  # noqa: B018


def test_a_struct_s_tuple_has_no_defaults():
    """A struct's tuple is built from every field."""
    with pytest.raises(TypeError, match="accelPlatform"):
        Gnc.ImuReading(angVelPlatform=np.zeros(3))


def test_unwritten_telemetry_is_none_and_written_telemetry_is_not():
    """Every telemetry field defaults to None; one written holds its value."""
    position = np.array([6871.0e3, 0.0, 0.0])

    telemetry = Gnc.ImuDeadReckonerTelemetry(bodyEciPos=position, navState="initialized")

    assert telemetry.bodyEciPos is position
    assert telemetry.navState == "initialized"
    assert telemetry.bodyEciVel is None
    assert telemetry.bodyEciAttitude is None
    assert Gnc.ImuDeadReckonerTelemetry() == (None, None, None, None)


def test_the_dead_reckoner_has_no_outputs_and_no_parameters():
    """The dead reckoner's FPP declares neither, so both tuples are empty."""
    assert Gnc.ImuDeadReckonerOutputs() == ()
    assert Gnc.ImuDeadReckonerParameters() == ()


def test_only_an_algorithm_s_component_gets_tuples():
    """A framework component, which no algorithm file defines, has none."""
    assert not hasattr(Svc, "CommandDispatcherTelemetry")
    assert not hasattr(Gnc, "Vector3")


def test_the_tuples_are_immutable_and_their_fields_pass_into_numba():
    """A field cannot be reassigned, and a tuple and its arrays are numba arguments."""
    reading = Gnc.ImuReading(angVelPlatform=np.ones(3), accelPlatform=np.full(3, 2.0))
    with pytest.raises(AttributeError):
        reading.angVelPlatform = np.zeros(3)

    @numba.njit
    def norm(v: np.ndarray) -> float:
        """A vector's length.

        Args:
            v: the vector.

        Returns:
            Its length.
        """
        return np.sqrt((v * v).sum())

    @numba.njit
    def total(r: tuple) -> float:
        """The sum of a reading's elements.

        Args:
            r: the reading.

        Returns:
            The sum.
        """
        return r.angVelPlatform.sum() + r.accelPlatform.sum()

    assert norm(reading.accelPlatform) == pytest.approx(np.sqrt(12.0))
    assert total(reading) == pytest.approx(9.0)


def test_a_parameter_has_a_default_only_when_fpp_gives_one(toy: SimpleNamespace):
    """Required parameters come first, in FPP's order, then the defaulted ones; missing one raises.

    Args:
        toy: the toy's namespace.
    """
    parameters = toy.SpinnerParameters

    assert parameters._fields == ("mounting", "count", "gain", "startMode")
    built = parameters(mounting=np.zeros(3), count=4)
    assert built.gain == 2.0
    assert built.startMode == "running"
    with pytest.raises(TypeError, match="count"):
        parameters(mounting=np.zeros(3))


def test_outputs_are_one_field_per_output_port_defaulting_to_none(toy: SimpleNamespace):
    """Each general output port is a field, unwritten by default.

    Args:
        toy: the toy's namespace.
    """
    assert toy.SpinnerOutputs._fields == ("readingOut", "gainOut")
    assert toy.SpinnerOutputs() == (None, None)
    assert toy.SpinnerTelemetry._fields == ("speed", "mode")


def test_a_converter_copies_arrays_and_passes_scalars_and_enum_names(toy: SimpleNamespace):
    """Array fields become fresh arrays of the FPP type; scalars and enum names pass as they are.

    Args:
        toy: the toy's namespace.
    """
    source = toy.Reading(rate=[1, 2, 3], count=4, mode="running")

    converted = converter(toy.Reading, toy.Reading)(source)

    assert converted.rate.dtype == np.dtype("float64")
    assert converted.rate.tolist() == [1.0, 2.0, 3.0]
    assert converted.count == 4
    assert converted.mode == "running"


def test_a_converter_keeps_each_array_s_shape_and_element_type(toy: SimpleNamespace):
    """An array of arrays keeps its nested shape, and an inline array its element's type.

    Args:
        toy: the toy's namespace.
    """
    source = toy.Shapes(rows=[[1, 2, 3], [4, 5, 6]], counts=[7, 8])

    converted = converter(toy.Shapes, toy.Shapes)(source)

    assert converted.rows.shape == (2, 3)
    assert converted.rows.dtype == np.dtype("float64")
    assert converted.counts.dtype == np.dtype("uint16")
    assert converted.counts.tolist() == [7, 8]


def test_a_converter_to_a_nested_struct_field_fails_naming_it(toy: SimpleNamespace):
    """A target field of struct type is not converted.

    Args:
        toy: the toy's namespace.
    """
    with pytest.raises(ValueError, match="inner"):
        converter(toy.Outer, toy.Outer)


@pytest.mark.parametrize(
    ("port", "replacement"),
    [
        ("output port gainOut: Gain", "output port gainOut: Pair"),
        ("output port gainOut: Gain", "output port gainOut: [2] Gain"),
    ],
    ids=["two arguments", "port array"],
)
def test_an_output_port_that_is_not_one_value_fails_generation_naming_it(
    tmp_path: Path, port: str, replacement: str
):
    """An output port with other than one argument, or an array of ports, has no field.

    Args:
        tmp_path: where the seeded toy is written.
        port: the toy's line seeded.
        replacement: the seeded line.
    """
    seeded = TOY.replace(port, replacement)
    assert seeded != TOY

    with pytest.raises(ValueError, match="gainOut"):
        _toy(tmp_path, seeded)
