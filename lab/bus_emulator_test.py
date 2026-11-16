"""The bus emulator's bytes for a Basilisk message are F´'s serialization of its bus struct.

The pin test is skipped without the deployment `just fsw` builds, as the `fsw` fixture skips.
"""

import struct
from types import ModuleType
from typing import Any

import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fpp_model import Member, Struct
from lab import bus_emulator
from lab.bus_emulator import serialize


def _fields(message: Any, order: str = ">") -> bytes:
    """An IMU message's four 3-vectors packed as twelve F64s in `Bus.fpp`'s order.

    Args:
        message: the IMU message.
        order: the `struct` byte order.

    Returns:
        The bytes.
    """
    m = message
    vectors = (m.DVFramePlatform, m.AccelPlatform, m.DRFramePlatform, m.AngVelPlatform)
    return struct.pack(f"{order}12d", *(value for vector in vectors for value in vector))


def test_an_imu_message_is_its_fields_big_endian_and_packed_in_declaration_order(
    imu_message: Any,
) -> None:
    """The IMU's bytes are its four 3-vectors as twelve big-endian F64s, in `Bus.fpp`'s order.

    Args:
        imu_message: the IMU message.
    """
    assert serialize(imu_message) == _fields(imu_message)


def test_the_same_fields_little_endian_are_other_bytes(imu_message: Any) -> None:
    """The comparison above tells byte orders apart: the same fields little-endian differ.

    Args:
        imu_message: the IMU message.
    """
    assert serialize(imu_message) != _fields(imu_message, "<")


def test_a_message_with_no_bus_struct_is_refused_by_name() -> None:
    """A payload that no `Bus.<Name>` mirrors raises `KeyError` naming it."""
    with pytest.raises(KeyError, match="SCStatesMsgPayload"):
        serialize(messaging.SCStatesMsgPayload())


@pytest.mark.parametrize(
    ("member", "named"),
    [
        (Member("count", "F64", None), "count is F64"),
        (Member("flags", "bool", 3), r"flags is \[3\] bool"),
        (Member("ticks", "U32", 3), r"ticks is \[3\] U32"),
    ],
    ids=["scalar", "bool", "unused-primitive"],
)
def test_a_member_outside_the_emulator_s_domain_is_refused_by_name(
    member: Member, named: str, imu_message: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scalar, `bool` or unused-primitive member raises `KeyError` naming it, when planned.

    The IMU's bus struct is stood in for by one with the member, and the packers are replanned.

    Args:
        member: the member outside the domain.
        named: the member as the refusal names it, a pattern.
        imu_message: the IMU message, whose packer is planned.
        monkeypatch: replaces the IMU's bus struct for the test.
    """
    toy = Struct("Bus.ImuSensorMsg", (Member("angVelPlatform", "F64", 3), member))
    monkeypatch.setitem(bus_emulator._STRUCTS, "imusensormsgpayload", toy)
    bus_emulator._packer.cache_clear()
    with pytest.raises(KeyError, match=rf"Bus\.ImuSensorMsg\.{named}, which the bus emulator"):
        serialize(imu_message)
    bus_emulator._packer.cache_clear()


def test_the_emulator_writes_the_bytes_f_prime_serializes(
    fsw: ModuleType, imu_message: Any
) -> None:
    """F´'s serialization of `Bus.ImuSensorMsg` from the same fields equals the emulator's bytes.

    A dv/dr-swapped or little-endian emulator's bytes differ from F´'s, so the check can fail.

    Args:
        fsw: a copy of the deployment.
        imu_message: the IMU message.
    """
    m = imu_message
    serialized = fsw.bus_ImuSensorMsg(
        dvFramePlatform=m.DVFramePlatform,
        accelPlatform=m.AccelPlatform,
        drFramePlatform=m.DRFramePlatform,
        angVelPlatform=m.AngVelPlatform,
    )
    assert serialize(m) == serialized
    assert _fields(m, "<") != serialized
    m.DVFramePlatform, m.DRFramePlatform = m.DRFramePlatform, m.DVFramePlatform
    assert serialize(m) != serialized
