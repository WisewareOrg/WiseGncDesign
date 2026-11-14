"""The Python build's RIO-in reads each paired role's Basilisk message as its bus struct."""

import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fpp_types import Bus, Gnc
from fsw.python.cdh.inputs import Pair
from fsw.python.rio.messages import commands, read

IMU = Pair("imu", Bus.ImuSensorMsg, Gnc.ImuReading, "imuIn")
"""A pair: the IMU's message, through its bus struct, to the GNC's reading."""


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


def test_each_paired_role_s_message_is_read_as_its_bus_struct():
    """The IMU's payload is read as a `Bus.ImuSensorMsg` of float64 arrays; other roles are not."""
    message = messaging.IMUSensorMsg()
    message.write(_payload([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))
    reader = _reader(message)

    read_ = read([IMU], {"imu": reader(), "other": object()})

    assert list(read_) == ["imu"]
    message = read_["imu"]
    assert isinstance(message, Bus.ImuSensorMsg)
    np.testing.assert_array_equal(message.angVelPlatform, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(message.accelPlatform, [4.0, 5.0, 6.0])
    assert message.angVelPlatform.dtype == np.float64


def test_a_payload_swig_returns_as_another_module_s_class_reads_alike():
    """Once `imuSensor` is imported, a reader's payload is its class, which declares no fields."""
    from Basilisk.simulation import imuSensor

    message = messaging.IMUSensorMsg()
    message.write(_payload([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))
    payload = _reader(message)()
    assert type(payload) is imuSensor.IMUSensorMsgPayload

    message = read([IMU], {"imu": payload})["imu"]

    np.testing.assert_array_equal(message.angVelPlatform, [1.0, 2.0, 3.0])


def test_a_read_message_keeps_its_values_after_the_next_tick():
    """The host's payload is a live view of the reader's buffer; the conversion copies it.

    Read, and the message written again, as the next tick's sensor task does: the bus struct
    still holds the first tick's values.
    """
    message = messaging.IMUSensorMsg()
    message.write(_payload([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))
    reader = _reader(message)
    payload = reader()
    read_ = read([IMU], {"imu": payload})["imu"]

    message.write(_payload([7.0, 8.0, 9.0], [0.0, 0.0, 0.0]))

    assert list(payload.AngVelPlatform) == [7.0, 8.0, 9.0]
    np.testing.assert_array_equal(read_.angVelPlatform, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(read_.accelPlatform, [4.0, 5.0, 6.0])


def test_a_paired_role_the_vehicle_does_not_have_is_refused_naming_it():
    """The configuration takes the IMU; a vehicle without one fails the tick, naming the role."""
    with pytest.raises(KeyError, match="imu"):
        read([IMU], {"star": object()})


def test_rio_out_commands_no_actuator():
    """No actuator is written, so RIO-out returns no command."""
    assert commands() == {}
