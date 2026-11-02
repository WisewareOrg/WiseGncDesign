"""The Basilisk transport's resolution of the data dictionary: the reader type and payload
field behind each input (role, signal), and the output message and payload field behind each
output (role, signal)."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import NamedTuple

from Basilisk.architecture import messaging

__all__ = ["INPUT_SIGNALS", "OUTPUT_SIGNALS", "InputField", "OutputField"]


class InputField(NamedTuple):
    """Where an input signal is read: a reader of type `reader_type`, field `payload_field`."""

    reader_type: type
    payload_field: str


class OutputField(NamedTuple):
    """Where an output signal is written: field `payload_field` of the output message named
    `message`, of type `message_type`."""

    message: str
    message_type: type
    payload_field: str


INPUT_SIGNALS: Mapping[tuple[str, str], InputField] = MappingProxyType(
    {
        ("imu", "angular_rate"): InputField(messaging.IMUSensorMsgReader, "AngVelPlatform"),
        ("imu", "specific_force"): InputField(messaging.IMUSensorMsgReader, "AccelPlatform"),
    }
)

OUTPUT_SIGNALS: Mapping[tuple[str, str], OutputField] = MappingProxyType(
    {
        ("navigation", "sigma_BN"): OutputField("nav_att", messaging.NavAttMsg, "sigma_BN"),
        ("navigation", "r_N"): OutputField("nav_trans", messaging.NavTransMsg, "r_BN_N"),
        ("navigation", "v_N"): OutputField("nav_trans", messaging.NavTransMsg, "v_BN_N"),
    }
)
