"""The Python build's CDH-in pairs each sensor role from FPP and converts its bus struct to ICD.

The deployment's own pairing is read from the contract and the dead reckoner's sub-topology; the
refusals are read from toy models of a converter and a sub-topology.
"""

from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.deployment import contract_files, framework_files
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.fpp_types import Bus, Gnc
from fsw.python.cdh.inputs import Pair, convert, pairings

_REPOSITORY = Path(__file__).resolve().parents[3]

CDH = """\
module Cdh {
  passive component BusConverter {
    sync input port imuIn: Bus.ImuSensorMsg
    output port imuOut: Gnc.ImuReading
  }
}
"""

SUB_TOPOLOGY = """\
module Toy {

  passive component Reader {
    sync input port schedIn: Svc.Sched
    sync input port imuIn: Gnc.ImuReading
  }

  instance rateGroupDriver: Svc.RateGroupDriver base id 0x400
  instance readerRateGroup: Svc.PassiveRateGroup base id 0x1100
  instance reader: Reader base id 0x2000

  topology Gnc {
    instance rateGroupDriver
    instance readerRateGroup
    instance reader
    connections RateGroups {
      rateGroupDriver.CycleOut[0] -> readerRateGroup.CycleIn
      readerRateGroup.RateGroupMemberOut[0] -> reader.schedIn
    }
    port tickIn = rateGroupDriver.CycleIn
    port imuIn = reader.imuIn
  }

}
"""


def _model(directory: Path, cdh: str = CDH, sub_topology: str = SUB_TOPOLOGY) -> Model:
    """A toy converter and sub-topology's model, with the framework and the interfaces.

    Args:
        directory: where `Cdh.fpp` and `Toy.fpp` are written.
        cdh: the converter's FPP.
        sub_topology: the sub-topology's FPP.

    Returns:
        The model.
    """
    (directory / "Cdh.fpp").write_text(cdh)
    (directory / "Toy.fpp").write_text(sub_topology)
    interfaces = _REPOSITORY / "fsw" / "fpp" / "interfaces"
    return read(
        [
            *framework_files(),
            interfaces / "Bus.fpp",
            interfaces / "Interfaces.fpp",
            directory / "Cdh.fpp",
            directory / "Toy.fpp",
        ]
    )


def test_the_deployment_pairs_the_imu_role_to_its_gnc_port():
    """`Cdh.BusConverter`'s `imuIn`/`imuOut` pair the IMU's bus struct to the GNC's reading."""
    gnc = _REPOSITORY / "fsw" / "fpp" / "gnc" / "ImuDeadReckoning.fpp"
    model = read([*contract_files(), gnc])

    assert pairings(model, "ImuDeadReckoning") == [
        Pair("imu", Bus.ImuSensorMsg, Gnc.ImuReading, "imuIn")
    ]


def test_a_role_the_configuration_does_not_take_is_skipped(tmp_path: Path):
    """A converter role with no sub-topology port of its name is not paired.

    Args:
        tmp_path: where the toy is written.
    """
    sub_topology = SUB_TOPOLOGY.replace("    port imuIn = reader.imuIn\n", "").replace(
        "    sync input port imuIn: Gnc.ImuReading\n", ""
    )

    assert pairings(_model(tmp_path, sub_topology=sub_topology), "Toy") == []


def test_a_role_without_its_output_is_refused_naming_it(tmp_path: Path):
    """Each bus-typed `<role>In` needs `<role>Out`, which the GNC's type is carried on.

    Args:
        tmp_path: where the toy is written.
    """
    cdh = CDH.replace("output port imuOut: Gnc.ImuReading", "output port rateOut: Gnc.ImuReading")

    with pytest.raises(ValueError, match="role imu"):
        pairings(_model(tmp_path, cdh=cdh), "Toy")


def test_a_role_whose_output_is_a_bus_struct_is_refused_naming_it(tmp_path: Path):
    """A bus-typed input converts to the GNC's type, never to another bus struct.

    Args:
        tmp_path: where the toy is written.
    """
    cdh = CDH.replace("output port imuOut: Gnc.ImuReading", "output port imuOut: Bus.ImuSensorMsg")

    with pytest.raises(ValueError, match="role imu"):
        pairings(_model(tmp_path, cdh=cdh), "Toy")


def test_a_sub_topology_input_no_role_feeds_is_refused_naming_it(tmp_path: Path):
    """A data input of the sub-topology with no converter pair would never be written.

    Args:
        tmp_path: where the toy is written.
    """
    sub_topology = SUB_TOPOLOGY.replace(
        "    port imuIn = reader.imuIn\n", "    port starIn = reader.imuIn\n"
    )

    with pytest.raises(ValueError, match=r"Toy\.Gnc\.starIn"):
        pairings(_model(tmp_path, sub_topology=sub_topology), "Toy")


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
