"""The F´ ground station: names to command packets, and telemetry bytes to values.

The codec runs against a toy component's dictionary, generated from FPP alone. The packets that
reach the deployment crafted or malformed need the deployment `just fsw` builds, and skip without
it.
"""

import importlib.util
import json
import struct
from types import ModuleType

import numpy as np
import pytest
from Basilisk.architecture import messaging

from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY, FprimeModule
from lab.power_cycle import power_cycle

BUILT = importlib.util.find_spec("lab._wise_fsw") is not None
"""Whether `just fsw` built the deployment; the tests that need it skip without it."""

TOY = """\
module Toy {

  enum Mode {
    slow
    fast
  }

  passive component Toy {
    sync command setToy(
      gain: F32
      enabled: bool
      mode: Mode
      offset: Gnc.Vector3
      mounting: Gnc.Matrix3
      count: U8
    )
    sync command label(note: string)
    telemetry gain: F32
    telemetry enabled: bool
    telemetry mode: Mode
    telemetry offset: Gnc.Vector3 format "{} m"
    telemetry mounting: Gnc.Matrix3
    time get port timeCaller
    telemetry port tlmOut
    command reg port cmdRegOut
    command recv port cmdIn
    command resp port cmdResponseOut
  }

}
"""

MOUNTING = np.arange(9.0).reshape(3, 3)

ARGS = {
    "gain": 0.1,
    "enabled": True,
    "mode": "fast",
    "offset": [1.0, 2.0, 3.0],
    "mounting": MOUNTING,
    "count": 7,
}

MU = 3.986004360e14
"""m^3/s^2, Earth's gravitational parameter, as the scenarios set it."""

NS = 1_000_000_000
"""ns per s."""

STATE = {
    "epoch": 0.0,
    "attitude": np.array([1.0, 0.0, 0.0, 0.0]),
    "position": np.array([6871.0e3, 0.0, 0.0]),
    "velocity": np.array([0.0, 5.4e3, 5.4e3]),
}
"""`nav.initNavState`'s arguments: a state at t = 0."""

WISE_FSW = Dictionary(DICTIONARY) if DICTIONARY.exists() else None
"""The deployment's dictionary, which the build generated, or `None` without the build."""


@pytest.fixture(scope="module")
def toy_dictionary(tmp_path_factory: pytest.TempPathFactory) -> Dictionary:
    """The toy's dictionary, instanced as `toy`.

    Args:
        tmp_path_factory: where the toy's model is written.

    Returns:
        The dictionary.
    """
    model = tmp_path_factory.mktemp("toy") / "Toy.fpp"
    model.write_text(TOY)
    return Dictionary.from_component([model], "Toy.Toy", instance="toy")


@pytest.fixture(scope="module")
def toy(toy_dictionary: Dictionary) -> FprimeStation:
    """A station for the toy on no deployment: its codec only.

    Args:
        toy_dictionary: the toy's dictionary.

    Returns:
        The station.
    """
    return FprimeStation(ModuleType("no_deployment"), toy_dictionary)


@pytest.fixture
def wise_fsw() -> ModuleType:
    """A fresh copy of the deployment, or a skip without the build.

    Returns:
        The copy, not yet booted.
    """
    if not BUILT:
        pytest.skip("the F´ build is absent; run `just fsw`")
    return power_cycle()


@pytest.fixture
def station(wise_fsw: ModuleType) -> FprimeStation:
    """A station on the deployment, booted idle and mounted at identity.

    Args:
        wise_fsw: the test's copy of the deployment.

    Returns:
        The station.
    """
    wise_fsw.boot(mu=MU, dcm_PB=np.eye(3))
    return FprimeStation(wise_fsw, WISE_FSW)


def test_a_command_packet_is_f_prime_s(toy: FprimeStation, toy_dictionary: Dictionary):
    """Descriptor, opcode, then big-endian arguments; an F32 is truncated and a bool is 0xFF.

    Args:
        toy: the toy's station.
        toy_dictionary: the toy's dictionary, which types the arguments.
    """
    packet = toy.encode_command("toy.setToy", toy_dictionary.arguments("toy.setToy", ARGS))

    assert packet[:6] == struct.pack(">HI", 0, 0x1000)
    assert packet[6:10] == struct.pack(">f", 0.1)
    assert packet[10] == 0xFF
    assert packet[11:15] == struct.pack(">i", 1)
    assert packet[15:39] == struct.pack(">3d", 1.0, 2.0, 3.0)
    assert packet[39:111] == struct.pack(">9d", *range(9))
    assert packet[111:] == bytes([7])


def test_a_command_the_dictionary_lacks_is_refused_naming_it(toy: FprimeStation):
    """Encoding a name the dictionary lacks raises `KeyError` naming it.

    Args:
        toy: the toy's station.
    """
    with pytest.raises(KeyError, match="'toy.setTyo'"):
        toy.encode_command("toy.setTyo", {})


@pytest.mark.parametrize(
    ("name", "args", "error", "match"),
    [
        ("toy.setToy", {k: v for k, v in ARGS.items() if k != "mode"}, KeyError, "'mode'"),
        ("toy.label", {"note": "hello"}, ValueError, r"toy\.label has a parameter type"),
    ],
    ids=["missing-argument", "type-not-coded"],
)
def test_a_command_the_station_cannot_encode_is_refused_naming_what(
    toy: FprimeStation, name: str, args: dict, error: type, match: str
):
    """A missing argument, or a parameter of a type not coded, raises naming it.

    Args:
        toy: the toy's station.
        name: the command encoded.
        args: its arguments.
        error: what encoding raises.
        match: what the error names.
    """
    with pytest.raises(error, match=match):
        toy.encode_command(name, args)


def test_serialized_writes_become_values_in_one_batch(toy: FprimeStation):
    """Arrays come back (N, *shape), a bool as 1.0, an enum as its name, an F32 as F32 holds it.

    Args:
        toy: the toy's station.
    """
    np.testing.assert_array_equal(
        toy.values("toy.offset", [struct.pack(">3d", 1, 2, 3), struct.pack(">3d", 4, 5, 6)]),
        [[1, 2, 3], [4, 5, 6]],
    )
    mounting = toy.values("toy.mounting", [struct.pack(">9d", *range(9))])
    np.testing.assert_array_equal(mounting[0], MOUNTING)
    assert toy.values("toy.enabled", [b"\xff", b"\x00"]).tolist() == [1.0, 0.0]
    assert toy.values("toy.mode", [struct.pack(">i", 1)]).tolist() == ["fast"]
    assert toy.values("toy.gain", [struct.pack(">f", 0.1)]).tolist() == [float(np.float32(0.1))]
    assert toy.values("toy.offset", []).shape == (0, 3)
    assert toy.values("toy.mode", []).shape == (0,)


@pytest.mark.parametrize(
    ("channel", "serialized"),
    [
        ("toy.gain", [0.5]),
        ("toy.offset", [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]),
        ("toy.offset", [struct.pack(">2d", 1.0, 2.0)]),
        ("toy.offset", [struct.pack(">2d", 1.0, 2.0), struct.pack(">4d", 3.0, 4.0, 5.0, 6.0)]),
    ],
    ids=["number", "numpy-array", "wrong-length", "misaligned"],
)
def test_values_takes_whole_serialized_values_only(
    toy: FprimeStation, channel: str, serialized: list
):
    """Written values, numpy arrays included, or bytes of the wrong length fail, naming the channel.

    Args:
        toy: the toy's station.
        channel: the channel decoded.
        serialized: what is handed to `values`.
    """
    with pytest.raises(ValueError, match=rf"channel {channel} "):
        toy.values(channel, serialized)


def _init() -> bytes:
    """`nav.initNavState` with `STATE`, as the station encodes it.

    Returns:
        The packet.
    """
    station = FprimeStation(ModuleType("no_deployment"), WISE_FSW)
    return station.encode_command("nav.initNavState", WISE_FSW.arguments("nav.initNavState", STATE))


def _unknown_opcode() -> int:
    """An opcode no instance of the deployment has.

    Returns:
        One past the largest opcode.
    """
    return max(c["opcode"] for c in json.loads(DICTIONARY.read_text())["commands"]) + 1


def _step(wise_fsw: ModuleType, t_ns: int) -> None:
    """Steps the deployment to `t_ns` on a zero IMU reading.

    Args:
        wise_fsw: the test's copy of the deployment.
        t_ns: ns, the tick's time.
    """
    wise_fsw.step(t_ns=t_ns, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))


def _writes(station: FprimeStation) -> list[tuple[str, int, object]]:
    """Drains the telemetry writes and keeps nav's, as values.

    Args:
        station: the station.

    Returns:
        Each of nav's writes' channel name, F´ time tag in ns and value, oldest first.
    """
    writes = station.telemetry()
    return [
        (name, t, station.values(name, [raw])[0])
        for name, t, raw in writes
        if name.startswith("nav.")
    ]


@pytest.mark.parametrize(
    ("change", "response"),
    [
        (lambda init: init[:2] + _unknown_opcode().to_bytes(4, "big") + init[6:], "INVALID_OPCODE"),
        (lambda init: b"\x00\x01" + init[2:], "VALIDATION_ERROR"),
        (lambda init: init[:4], "VALIDATION_ERROR"),
        (lambda init: init[:-8], "FORMAT_ERROR"),
        (lambda init: init[:6], "FORMAT_ERROR"),
        (lambda init: init + bytes(8), "FORMAT_ERROR"),
    ],
    ids=[
        "unknown-opcode",
        "not-a-command",
        "truncated-head",
        "short-arguments",
        "no-arguments",
        "extra",
    ],
)
def test_a_rejected_packet_gets_f_prime_s_response_by_name_and_nav_stays_idle(
    wise_fsw: ModuleType, station: FprimeStation, change: object, response: str
):
    """F´ answers a bad packet with its `Fw.CmdResponse`, named, with no reason, and runs nothing.

    Args:
        wise_fsw: the test's copy of the deployment.
        station: the station on it.
        change: makes the bad packet from a good `nav.initNavState`.
        response: the response F´ gives it.
    """
    wise_fsw.uplink(change(_init()), 7)
    _step(wise_fsw, NS)

    assert station.responses() == [(7, response, None)]
    assert _writes(station) == [("nav.navState", NS, "idle")]


@pytest.mark.skipif(not BUILT, reason="the F´ build is absent; run `just fsw`")
def test_a_command_f_prime_rejects_fails_nothing_in_the_f_prime_host():
    """Through the F´ host, an opcode no instance has is answered `INVALID_OPCODE`, no reason."""
    module = FprimeModule(messaging.IMUSensorMsgReader(), mu=MU, dcm_PB=np.eye(3))
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)
    init = _init()

    module._fsw.uplink(init[:2] + _unknown_opcode().to_bytes(4, "big") + init[6:], 9)
    module.UpdateState(NS)

    assert module.responses() == [(9, "INVALID_OPCODE", None)]
    assert module.failure is None
