"""The Python build's CDH-in converts each role's Basilisk message to its GNC input's FPP type."""

import numpy as np
from Basilisk.architecture import messaging

from fsw.codegen.fpp_types import Bus, Gnc
from fsw.python.cdh.inputs import Pair, convert

IMU = Pair("imu", Bus.ImuSensorMsg, Gnc.ImuReading, "imuIn")
"""A toy pair: the IMU's message, through its bus struct, to the dead reckoner's reading."""


def _reader(message: messaging.IMUSensorMsg) -> messaging.IMUSensorMsgReader:
    """A reader subscribed to a message, as a vehicle's is.

    Args:
        message: the message.

    Returns:
        The reader.
    """
    reader = messaging.IMUSensorMsgReader()
    reader.subscribeTo(message)
    return reader


def _payload(rate: list[float], accel: list[float]) -> messaging.IMUSensorMsgPayload:
    """An IMU payload.

    Args:
        rate: rad/s, its angular velocity.
        accel: m/s^2, its acceleration.

    Returns:
        The payload.
    """
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = rate
    payload.AccelPlatform = accel
    return payload


def test_each_role_s_message_reaches_its_gnc_port_in_the_icd_type():
    """The IMU's payload arrives at `imuIn` as a `Gnc.ImuReading` of float64 arrays."""
    message = messaging.IMUSensorMsg()
    message.write(_payload([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))
    reader = _reader(message)

    converted = convert([IMU], {"imu": reader(), "other": object()})

    assert list(converted) == ["imuIn"]
    reading = converted["imuIn"]
    assert isinstance(reading, Gnc.ImuReading)
    np.testing.assert_array_equal(reading.angVelPlatform, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(reading.accelPlatform, [4.0, 5.0, 6.0])
    assert reading.angVelPlatform.dtype == np.float64


def test_a_payload_swig_returns_as_another_module_s_class_converts_alike():
    """Once `imuSensor` is imported, a reader's payload is its class, which declares no fields."""
    from Basilisk.simulation import imuSensor

    message = messaging.IMUSensorMsg()
    message.write(_payload([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))
    payload = _reader(message)()
    assert type(payload) is imuSensor.IMUSensorMsgPayload

    reading = convert([IMU], {"imu": payload})["imuIn"]

    np.testing.assert_array_equal(reading.angVelPlatform, [1.0, 2.0, 3.0])


def test_a_converted_reading_keeps_its_values_after_the_next_tick():
    """The host's payload is a live view of the reader's buffer; the conversion copies it.

    Read, converted, and the message written again, as the next tick's sensor task does: the
    reading still holds the first tick's values.
    """
    message = messaging.IMUSensorMsg()
    message.write(_payload([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))
    reader = _reader(message)
    payload = reader()
    reading = convert([IMU], {"imu": payload})["imuIn"]

    message.write(_payload([7.0, 8.0, 9.0], [0.0, 0.0, 0.0]))

    assert list(payload.AngVelPlatform) == [7.0, 8.0, 9.0]
    np.testing.assert_array_equal(reading.angVelPlatform, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(reading.accelPlatform, [4.0, 5.0, 6.0])
