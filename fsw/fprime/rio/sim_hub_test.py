"""SimHub delivers the bus emulator's bytes to the typed bus port, and wrong-length bytes raise.

On a booted copy of the deployment: F´ deserializes the bytes pushed on SimHub's port into the
bus struct the port connects to, and a push of the wrong length trips F´'s own assert, which
raises in Python. Skipped without the deployment `just fsw` builds, as the `fsw` fixture skips.
"""

from types import ModuleType
from typing import Any

import pytest

from lab.bus_emulator import serialize

NS = 1_000_000_000
"""ns per s."""


def test_the_imu_message_s_bytes_step_cleanly(
    fsw: ModuleType, prm: str, parameter_ids: list[int], imu_message: Any, imu_port: int
) -> None:
    """The emulator's 96 bytes for an IMU message step the deployment.

    Args:
        fsw: a copy of the deployment.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_message: the IMU message.
        imu_port: the IMU's SimHub port.
    """
    fsw.boot(prm, parameter_ids)
    data = serialize(imu_message)
    assert len(data) == 96

    fsw.step(t_ns=NS, bus=[(imu_port, data)])


@pytest.mark.parametrize("length", [95, 97])
def test_a_push_of_the_wrong_length_raises(
    fsw: ModuleType,
    prm: str,
    parameter_ids: list[int],
    imu_message: Any,
    imu_port: int,
    length: int,
) -> None:
    """Bytes one short of the IMU message, or one over, trip F´'s assert, raised in Python.

    Args:
        fsw: a copy of the deployment.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        imu_message: the IMU message.
        imu_port: the IMU's SimHub port.
        length: the bytes pushed.
    """
    fsw.boot(prm, parameter_ids)
    data = (serialize(imu_message) + b"\0")[:length]

    with pytest.raises(RuntimeError, match=r'^Assert: ".*:\d+"'):
        fsw.step(t_ns=NS, bus=[(imu_port, data)])
