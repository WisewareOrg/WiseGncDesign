"""The generated `Cdh.BusConverter` converts the IMU's bus struct to `Gnc.ImuReading` in F´.

Through the test pin `cdh_imu`: the bus emulator's bytes for an IMU message, deserialized by F´,
converted by the generated conversion and serialized back. Skipped without the deployment
`just fsw` builds, as the `fsw` fixture skips.
"""

import struct
from types import ModuleType
from typing import Any

import pytest

from lab.bus_emulator import serialize


def test_the_imu_bus_struct_converts_to_the_imu_reading(fsw: ModuleType, imu_message: Any) -> None:
    """The reading's bytes are the message's angular velocity, then its acceleration.

    Args:
        fsw: a copy of the deployment.
        imu_message: the IMU message.
    """
    reading = struct.unpack(">6d", fsw.cdh_imu(serialize(imu_message)))
    assert list(reading) == [*imu_message.AngVelPlatform, *imu_message.AccelPlatform]


def test_the_pin_reads_the_bytes_by_the_bus_layout(fsw: ModuleType, imu_message: Any) -> None:
    """Bytes with angular velocity and dv in each other's place read dv as the angular velocity.

    Args:
        fsw: a copy of the deployment.
        imu_message: the IMU message.
    """
    m = imu_message
    swapped = struct.pack(
        ">12d", *m.AngVelPlatform, *m.AccelPlatform, *m.DRFramePlatform, *m.DVFramePlatform
    )
    reading = struct.unpack(">6d", fsw.cdh_imu(swapped))
    assert list(reading) == [*m.DVFramePlatform, *m.AccelPlatform]


def test_bytes_too_short_for_the_bus_struct_raise_naming_the_role(fsw: ModuleType) -> None:
    """Eight bytes cannot fill the IMU's 96, so F´'s deserialization fails, naming the role.

    Args:
        fsw: a copy of the deployment.
    """
    with pytest.raises(RuntimeError, match="cdh_imu: deserializing Bus.ImuSensorMsg failed"):
        fsw.cdh_imu(bytes(8))
