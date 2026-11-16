"""The generated `Cdh.BusConverter` converts the IMU's bus struct to `Gnc.ImuReading` in F´.

Through the test pin `cdh_imu`: the bus emulator's bytes for an IMU message, deserialized by F´,
converted by the generated conversion and serialized back. Skipped without the deployment
`just fsw` builds, as the `fsw` fixture skips.
"""

import struct
from types import ModuleType
from typing import Any

from lab.bus_emulator import serialize


def test_the_imu_bus_struct_converts_to_the_imu_reading(fsw: ModuleType, imu_message: Any) -> None:
    """The reading's bytes are the message's angular velocity, then its acceleration.

    Args:
        fsw: a copy of the deployment.
        imu_message: the IMU message.
    """
    reading = struct.unpack(">6d", fsw.cdh_imu(serialize(imu_message)))
    assert list(reading) == [*imu_message.AngVelPlatform, *imu_message.AccelPlatform]


def test_a_bus_layout_with_dv_and_angular_velocity_swapped_converts_to_other_values(
    fsw: ModuleType, imu_message: Any
) -> None:
    """Bytes laid out with dv where the angular velocity belongs give another reading.

    Args:
        fsw: a copy of the deployment.
        imu_message: the IMU message.
    """
    m = imu_message
    swapped = struct.pack(
        ">12d", *m.AngVelPlatform, *m.AccelPlatform, *m.DRFramePlatform, *m.DVFramePlatform
    )
    reading = struct.unpack(">6d", fsw.cdh_imu(swapped))
    assert list(reading) != [*m.AngVelPlatform, *m.AccelPlatform]
