"""The Python build's CDH-in pairs each sensor role from FPP and converts its bus struct to ICD.

The deployment's own pairing is read from the contract and the dead reckoner's sub-topology; the
refusals are read from a toy converter.
"""

from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.deployment import contract_files, framework_files
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.fpp_types import Bus, Gnc
from fsw.python.cdh.inputs import Pair, convert, pairings
from fsw.python.gnc.partition import GncPartition

_REPOSITORY = Path(__file__).resolve().parents[3]

CDH = """\
module Cdh {
  passive component BusConverter {
    sync input port imuIn: Bus.ImuSensorMsg
    output port imuOut: Gnc.ImuReading
  }
}
"""


def _model(directory: Path, cdh: str = CDH) -> Model:
    """A toy converter's model, with the framework and the interfaces.

    Args:
        directory: where `Cdh.fpp` is written.
        cdh: the converter's FPP.

    Returns:
        The model.
    """
    (directory / "Cdh.fpp").write_text(cdh)
    interfaces = _REPOSITORY / "fsw" / "fpp" / "interfaces"
    return read(
        [
            *framework_files(),
            interfaces / "Bus.fpp",
            interfaces / "Interfaces.fpp",
            directory / "Cdh.fpp",
        ]
    )


class ImuDeadReckoner:
    """A stub in the place of the deployment's sub-topology's one component."""


def test_the_deployment_pairs_the_imu_role_to_its_gnc_port():
    """`Cdh.BusConverter`'s `imuIn`/`imuOut` pair the IMU's bus struct to the GNC's reading."""
    gnc = _REPOSITORY / "fsw" / "fpp" / "gnc" / "ImuDeadReckoning.fpp"
    model = read([*contract_files(), gnc])
    ports = GncPartition(model, "ImuDeadReckoning", (ImuDeadReckoner,)).inputs

    assert pairings(model, ports) == [Pair("imu", Bus.ImuSensorMsg, Gnc.ImuReading, "imuIn")]


def test_a_role_the_sub_topology_does_not_take_is_skipped(tmp_path: Path):
    """A converter role with no sub-topology input of its name is not paired.

    Args:
        tmp_path: where the toy is written.
    """
    assert pairings(_model(tmp_path), ()) == []


def test_a_role_without_its_output_is_refused_naming_it(tmp_path: Path):
    """Each bus-typed `<role>In` needs `<role>Out`, which the GNC's type is carried on.

    Args:
        tmp_path: where the toy is written.
    """
    cdh = CDH.replace("output port imuOut: Gnc.ImuReading", "output port rateOut: Gnc.ImuReading")

    with pytest.raises(ValueError, match="role imu"):
        pairings(_model(tmp_path, cdh=cdh), ("imuIn",))


def test_a_role_whose_output_is_a_bus_struct_is_refused_naming_it(tmp_path: Path):
    """A bus-typed input converts to the GNC's type, never to another bus struct.

    Args:
        tmp_path: where the toy is written.
    """
    cdh = CDH.replace("output port imuOut: Gnc.ImuReading", "output port imuOut: Bus.ImuSensorMsg")

    with pytest.raises(ValueError, match="role imu"):
        pairings(_model(tmp_path, cdh=cdh), ("imuIn",))


def test_a_sub_topology_input_no_role_feeds_is_refused_naming_it(tmp_path: Path):
    """A data input of the sub-topology with no converter pair would never be written.

    Args:
        tmp_path: where the toy is written.
    """
    with pytest.raises(ValueError, match=r"\['starIn'\]"):
        pairings(_model(tmp_path), ("imuIn", "starIn"))


def test_a_bus_struct_is_converted_to_its_icd_struct_at_its_gnc_port():
    """The IMU's bus struct reaches `imuIn` as a fresh `Gnc.ImuReading`."""
    message = Bus.ImuSensorMsg(
        dvFramePlatform=np.zeros(3),
        accelPlatform=np.array([4.0, 5.0, 6.0]),
        drFramePlatform=np.zeros(3),
        angVelPlatform=np.array([1.0, 2.0, 3.0]),
    )

    converted = convert([Pair("imu", Bus.ImuSensorMsg, Gnc.ImuReading, "imuIn")], {"imu": message})
    message.angVelPlatform[0] = 9.0

    assert list(converted) == ["imuIn"]
    reading = converted["imuIn"]
    assert isinstance(reading, Gnc.ImuReading)
    np.testing.assert_array_equal(reading.angVelPlatform, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(reading.accelPlatform, [4.0, 5.0, 6.0])
