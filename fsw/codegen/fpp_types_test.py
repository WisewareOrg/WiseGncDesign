"""FPP's types as named tuples, and the converters between them, on the contract and on a mock.

Needs the F´ framework clone `just _sync` fetches, not an F´ build.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import numba
import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen import fpp_types
from fsw.codegen.deployment import (
    Contract,
    algorithm_components,
    configuration_model,
    framework_files,
)
from fsw.codegen.fpp_model import read
from fsw.codegen.fpp_types import Bus, Gnc, Svc, _build, converter, named, parameters_from
from fsw.mock import edited
from ground.dictionary import Dictionary

MOCK = """\
module Mock {

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

  struct FlatShapes {
    rows: [6] F64
    counts: [2] U16
  }

  struct WideShapes {
    rows: Rows
    counts: [2] U32
  }

  struct QuaternionRate {
    angVelPlatform: [4] F64
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


def _mock(directory: Path, mock: str = MOCK) -> dict[str, SimpleNamespace]:
    """The mock's types, its component an algorithm's.

    Args:
        directory: where `Mock.fpp` is written.
        mock: the mock's FPP.

    Returns:
        The namespaces `_build` makes, by top-level module.
    """
    algorithm = directory / "Mock.fpp"
    algorithm.write_text(mock)
    return _build(read([*framework_files(), algorithm]), {algorithm})


@pytest.fixture(scope="module")
def mock(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """The mock's namespace, built once.

    Args:
        tmp_path_factory: where the mock is written.

    Returns:
        Module `Mock`'s namespace.
    """
    return _mock(tmp_path_factory.mktemp("mock"))["Mock"]


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


def test_a_converter_to_a_tuple_that_is_not_a_struct_s_fails_naming_it():
    """Telemetry is no struct, so no converter to it is built."""
    with pytest.raises(ValueError, match="ImuDeadReckonerTelemetry"):
        converter(Bus.ImuSensorMsg, Gnc.ImuDeadReckonerTelemetry)


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


def test_a_parameter_has_a_default_only_when_fpp_gives_one(mock: SimpleNamespace):
    """Required parameters come first, in FPP's order, then the defaulted ones; missing one raises.

    Args:
        mock: the mock's namespace.
    """
    parameters = mock.SpinnerParameters

    assert parameters._fields == ("mounting", "count", "gain", "startMode")
    built = parameters(mounting=np.zeros(3), count=4)
    assert built.gain == 2.0
    assert built.startMode == "running"
    with pytest.raises(TypeError, match="count"):
        parameters(mounting=np.zeros(3))


def test_parameters_from_plain_values_makes_each_array_of_its_fpp_shape_and_type(
    mock: SimpleNamespace,
):
    """JSON-shaped values become the tuple: lists to fresh arrays, scalars as given, defaults kept.

    Args:
        mock: the mock's namespace.
    """
    built = parameters_from(mock.SpinnerParameters, {"mounting": [1, 2, 3], "count": 4})

    assert type(built) is mock.SpinnerParameters
    assert built.mounting.dtype == np.float64
    np.testing.assert_array_equal(built.mounting, [1.0, 2.0, 3.0])
    assert built.count == 4
    assert built.gain == 2.0
    nav = parameters_from(Gnc.ImuDeadReckonerParameters, {"mu": 1.0, "dcm_PB": np.eye(3).tolist()})
    assert nav.dcm_PB.shape == (3, 3)
    assert nav.dcm_PB.dtype == np.float64


def test_parameters_from_refuses_an_array_of_another_shape_naming_it(mock: SimpleNamespace):
    """A value whose shape is not the field's FPP shape fails, naming the field.

    Args:
        mock: the mock's namespace.
    """
    with pytest.raises(
        ValueError, match=r"Mock\.Spinner\.mounting is \(3,\), but its value is \(2,\)"
    ):
        parameters_from(mock.SpinnerParameters, {"mounting": [1.0, 2.0], "count": 4})


def test_outputs_are_one_field_per_output_port_defaulting_to_none(mock: SimpleNamespace):
    """Each general output port is a field, unwritten by default.

    Args:
        mock: the mock's namespace.
    """
    assert mock.SpinnerOutputs._fields == ("readingOut", "gainOut")
    assert mock.SpinnerOutputs() == (None, None)
    assert mock.SpinnerTelemetry._fields == ("speed", "mode")


def test_a_converter_copies_arrays_and_passes_scalars_and_enum_names(mock: SimpleNamespace):
    """Array fields become fresh arrays of the FPP type; scalars and enum names pass as they are.

    Args:
        mock: the mock's namespace.
    """
    source = mock.Reading(rate=[1, 2, 3], count=4, mode="running")

    converted = converter(mock.Reading, mock.Reading)(source)

    assert converted.rate.dtype == np.dtype("float64")
    assert converted.rate.tolist() == [1.0, 2.0, 3.0]
    assert converted.count == 4
    assert converted.mode == "running"


def test_a_converter_keeps_each_array_s_shape_and_element_type(mock: SimpleNamespace):
    """An array of arrays keeps its nested shape, and an inline array its element's type.

    Args:
        mock: the mock's namespace.
    """
    source = mock.Shapes(rows=[[1, 2, 3], [4, 5, 6]], counts=[7, 8])

    converted = converter(mock.Shapes, mock.Shapes)(source)

    assert converted.rows.shape == (2, 3)
    assert converted.rows.dtype == np.dtype("float64")
    assert converted.counts.dtype == np.dtype("uint16")
    assert converted.counts.tolist() == [7, 8]


@pytest.mark.parametrize(
    ("source", "field"),
    [("FlatShapes", "rows"), ("WideShapes", "counts")],
    ids=["flat array to an array of arrays", "U32 to U16"],
)
def test_a_converter_from_a_field_of_another_shape_or_type_fails_naming_it(
    mock: SimpleNamespace, source: str, field: str
):
    """A source field must have its target field's shape and element type.

    Args:
        mock: the mock's namespace.
        source: the source struct, whose `field` differs from `Shapes`'.
        field: the field that differs.
    """
    with pytest.raises(ValueError, match=field):
        converter(getattr(mock, source), mock.Shapes)


def test_a_converter_from_a_basilisk_field_of_another_shape_fails_naming_it(
    mock: SimpleNamespace,
):
    """Basilisk's three-element rate does not fill a four-element field.

    Args:
        mock: the mock's namespace.
    """
    with pytest.raises(ValueError, match="AngVelPlatform"):
        converter(messaging.IMUSensorMsgPayload, mock.QuaternionRate)


def test_a_converter_to_a_nested_struct_field_fails_naming_it(mock: SimpleNamespace):
    """A target field of struct type is not converted.

    Args:
        mock: the mock's namespace.
    """
    with pytest.raises(ValueError, match="inner"):
        converter(mock.Outer, mock.Outer)


@pytest.mark.parametrize(
    ("port", "replacement"),
    [
        ("output port gainOut: Gain", "output port gainOut: Pair"),
        ("output port gainOut: Gain", "output port gainOut: [2] Gain"),
        ("output port gainOut: Gain", "output port gainOut: serial"),
    ],
    ids=["two arguments", "port array", "serial"],
)
def test_an_output_port_that_is_not_one_value_fails_generation_naming_it(
    tmp_path: Path, port: str, replacement: str
):
    """An output port with other than one argument, or an array of ports, has no field.

    Args:
        tmp_path: where the seeded mock is written.
        port: the mock's line seeded.
        replacement: the seeded line.
    """
    with pytest.raises(ValueError, match="gainOut"):
        _mock(tmp_path, edited(MOCK, (port, replacement)))


def test_each_gnc_instance_s_tuples_name_its_dictionary_s_channels_parameters_and_ports(
    configuration: str,
):
    """Each algorithm instance's telemetry tuple writes exactly its dictionary's channels.

    Its parameters tuple holds the dictionary's parameters, and its outputs tuple its component's
    output ports, so a write named for a field is a channel the ground can pack.

    Args:
        configuration: the configuration.
    """
    dictionary = Dictionary.from_sub_topology(configuration)
    components = configuration_model(configuration).components
    instances = dictionary.algorithm_instances()
    assert instances
    for instance in instances:
        short = instance.name.rsplit(".", 1)[-1]
        component = instance.component
        channels = dictionary.entries(short)["channels"]
        parameters = [
            p.name.removeprefix(f"{short}.") for p in dictionary.parameters_by_id.values()
        ]
        ports = [p.name for p in components[component].outputs]
        assert sorted(named(f"{component}Telemetry")._fields) == sorted(channels), instance.name
        assert sorted(named(f"{component}Parameters")._fields) == sorted(parameters), instance.name
        assert list(named(f"{component}Outputs")._fields) == ports, instance.name


LOADED = """\
module MockLoaded {

  struct Sample {
    value: F64
  }

  passive component Probe {
    command recv port cmdIn
    command reg port cmdRegOut
    command resp port cmdResponseOut
    telemetry port tlmOut
    time get port timeCaller
    param get port prmGetOut
    param set port prmSetOut

    telemetry level: F64

    param gain: F64
  }

}
"""
"""A mock contract's algorithm: a module of its own, sharing no name with the repository's."""


def _contract(directory: Path, algorithm: str) -> Contract:
    """A contract of one algorithm file, with no GNC sub-topology.

    Args:
        directory: where the algorithm's `.fpp` and the empty GNC directory are written.
        algorithm: the algorithm's FPP.

    Returns:
        The contract.
    """
    path = directory / "Algorithm.fpp"
    path.write_text(algorithm)
    (directory / "gnc").mkdir()
    return Contract((path,), directory / "gnc")


def test_a_loaded_contract_s_tuples_resolve_and_the_repository_s_stay_as_they_are(
    tmp_path: Path,
):
    """After `load`, the contract's names resolve; the repository's namespaces and exports do not.

    Args:
        tmp_path: where the contract is written.
    """
    gnc, exports = dict(vars(Gnc)), list(fpp_types.__all__)

    fpp_types.load(_contract(tmp_path, LOADED))

    parameters = named("MockLoaded.ProbeParameters")
    assert parameters._fields == ("gain",)
    assert parameters.component == "MockLoaded.Probe"
    assert named("MockLoaded.ProbeTelemetry")._fields == ("level",)
    assert named("MockLoaded.Sample")._fields == ("value",)
    assert parameters_from(parameters, {"gain": 2.5}) == parameters(gain=2.5)
    assert dict(vars(Gnc)) == gnc
    assert fpp_types.__all__ == exports
    assert not hasattr(fpp_types, "MockLoaded")


def test_a_contract_redefining_a_generated_name_is_refused_naming_it(tmp_path: Path):
    """An algorithm component of the repository, defined again otherwise, raises naming it.

    Args:
        tmp_path: where the contract is written.
    """
    name = sorted(algorithm_components())[0]
    module, component = name.rsplit(".", 1)
    redefined = f"module {module} {{\n  passive component {component} {{\n  }}\n}}\n"

    with pytest.raises(ValueError, match=re.escape(name)):
        fpp_types.load(_contract(tmp_path, redefined))


def test_a_contract_s_new_name_in_an_existing_module_leaves_that_module_s_namespace_as_it_is(
    tmp_path: Path,
):
    """A struct a contract adds to a module the repository's has resolves, and the module does not.

    Args:
        tmp_path: where the contract is written.
    """
    gnc = dict(vars(Gnc))

    fpp_types.load(
        _contract(tmp_path, "module Gnc {\n  struct MockAdded {\n    value: F64\n  }\n}\n")
    )

    assert named("Gnc.MockAdded")._fields == ("value",)
    assert not hasattr(Gnc, "MockAdded")
    assert dict(vars(Gnc)) == gnc
