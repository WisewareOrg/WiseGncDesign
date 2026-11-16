"""The bus emulator's bytes for a Basilisk message are F´'s serialization of its bus struct.

The pin test is skipped without the deployment `just fsw` builds.
"""

import importlib.util
import struct

import pytest
from Basilisk.architecture import messaging

from lab.bus_emulator import serialize
from lab.power_cycle import power_cycle

_BUILT = importlib.util.find_spec("lab._wise_fsw") is not None
"""Whether the deployment's extension is built."""

DV = [0.1, -0.2, 0.3]
ACCEL = [1.5, -2.25, 9.80665]
DR = [0.004, -0.005, 0.006]
ANG_VEL = [0.07, -0.08, 0.09]
"""An IMU message's fields, every value distinct, so a field out of place shows."""


def _imu() -> messaging.IMUSensorMsgPayload:
    """An IMU message with the distinct field values.

    Returns:
        The message.
    """
    payload = messaging.IMUSensorMsgPayload()
    payload.DVFramePlatform = DV
    payload.AccelPlatform = ACCEL
    payload.DRFramePlatform = DR
    payload.AngVelPlatform = ANG_VEL
    return payload


def test_an_imu_message_is_its_fields_big_endian_and_packed_in_declaration_order() -> None:
    """The IMU's bytes are its four 3-vectors as twelve big-endian F64s, in `Bus.fpp`'s order."""
    assert serialize(_imu()) == struct.pack(">12d", *DV, *ACCEL, *DR, *ANG_VEL)


def test_the_same_fields_little_endian_are_other_bytes() -> None:
    """The comparison above tells byte orders apart: the same fields little-endian differ."""
    assert serialize(_imu()) != struct.pack("<12d", *DV, *ACCEL, *DR, *ANG_VEL)


def test_a_message_with_no_bus_struct_is_refused_by_name() -> None:
    """A payload that no `Bus.<Name>` mirrors raises `KeyError` naming it."""
    with pytest.raises(KeyError, match="SCStatesMsgPayload"):
        serialize(messaging.SCStatesMsgPayload())


@pytest.mark.skipif(not _BUILT, reason="the F´ build is absent; run `just fsw`")
def test_the_emulator_writes_the_bytes_f_prime_serializes() -> None:
    """F´'s serialization of `Bus.ImuSensorMsg` from the same fields equals the emulator's bytes.

    A dv/dr-swapped or little-endian emulator's bytes differ from F´'s, so the check can fail.
    """
    fields = {
        "dvFramePlatform": DV,
        "accelPlatform": ACCEL,
        "drFramePlatform": DR,
        "angVelPlatform": ANG_VEL,
    }
    serialized = power_cycle().bus_ImuSensorMsg(**fields)
    assert serialize(_imu()) == serialized
    assert struct.pack(">12d", *DR, *ACCEL, *DV, *ANG_VEL) != serialized
    assert struct.pack("<12d", *DV, *ACCEL, *DR, *ANG_VEL) != serialized
