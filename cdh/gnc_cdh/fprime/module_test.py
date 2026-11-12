"""The F´ host's refusals and its run-file datasets, against messages written by hand.

Needs the deployment `just fsw` builds.
"""

import json
import struct

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.fprime import DICTIONARY, FprimeModule, decoders

ONE_SECOND_NS = 1_000_000_000

INITIAL = {
    "sigma0_BN": np.array([0.1, 0.2, -0.3]),
    "r0_N": np.array([6871.0e3, 0.0, 0.0]),
    "v0_N": np.array([0.0, 5.4e3, 5.4e3]),
}
"""A dead reckoner's state at t = 0, in the shape of a scenario's `initial_state()`."""


def _module() -> FprimeModule:
    """A host on an unsubscribed IMU reader, mounted at identity.

    Returns:
        The `FprimeModule`.
    """
    return FprimeModule(
        messaging.IMUSensorMsgReader(), mu=3.986004360e14, dcm_PB=np.eye(3), initial=INITIAL
    )


def test_reset_refuses_an_unsubscribed_imu():
    """`Reset` names the IMU reader that no message feeds."""
    with pytest.raises(RuntimeError, match="IMU reader is not subscribed"):
        _module().Reset(0)


def test_a_tick_refuses_an_imu_never_written():
    """A tick after the reset names the IMU message that has never been written."""
    module = _module()
    imu = messaging.IMUSensorMsg()
    module._imu.subscribeTo(imu)
    module.Reset(0)

    with pytest.raises(RuntimeError, match=r"IMU has not been written at t = 1.0 s"):
        module.UpdateState(ONE_SECOND_NS)


def test_the_estimate_datasets_are_the_logged_ticks_and_refuse_a_time_never_logged():
    """`estimate_datasets` gives the state at each logged tick, and names a time no tick logged."""
    module = _module()
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)
    for tick in (1, 2, 3):
        module.UpdateState(tick * ONE_SECOND_NS // 10)

    datasets = module.estimate_datasets(np.array([0.0, 0.1, 0.2, 0.3]))

    assert sorted(datasets) == ["est/r_BN_N", "est/sigma_BN", "est/v_BN_N"]
    np.testing.assert_allclose(datasets["est/sigma_BN"][0][0], INITIAL["sigma0_BN"], atol=1e-15)
    np.testing.assert_array_equal(datasets["est/r_BN_N"][0][0], INITIAL["r0_N"])
    assert datasets["est/r_BN_N"][1] == "m"
    positions = datasets["est/r_BN_N"][0]
    assert len({tuple(row) for row in positions}) == len(positions)
    with pytest.raises(KeyError, match="no telemetry was logged at t = 0.25 s"):
        module.estimate_datasets(np.array([0.25]))


def _dictionary() -> dict:
    """The dictionary F´ generated for the deployment.

    Returns:
        The parsed JSON.
    """
    return json.loads(DICTIONARY.read_text())


def test_decoders_cover_every_channel_of_the_generated_dictionary():
    """Every channel the deployment declares has a decoder, named and typed as declared."""
    dictionary = _dictionary()
    channels = decoders(dictionary)

    assert dictionary["telemetryChannels"]
    assert sorted(channels) == sorted(c["id"] for c in dictionary["telemetryChannels"])
    assert sorted(name for name, _ in channels.values()) == sorted(
        c["name"].split(".", 1)[1] for c in dictionary["telemetryChannels"]
    )
    by_name = {name: decode for name, decode in channels.values()}
    assert by_name["nav.bodyEciPosX"](struct.pack(">d", 6871.0e3)) == 6871.0e3
    states = next(t for t in dictionary["typeDefinitions"] if t["qualifiedName"] == "Gnc.NavState")
    for constant in states["enumeratedConstants"]:
        raw = struct.pack(">i", constant["value"])
        assert by_name["nav.navState"](raw) == constant["name"]


def test_decoders_refuse_a_channel_of_a_type_they_cannot_decode_and_accept_a_primitive():
    """A channel retyped to a struct raises, naming channel and type; one retyped to F32 decodes."""
    dictionary = _dictionary()
    channel = dictionary["telemetryChannels"][1]
    dictionary["telemetryChannels"][1] = channel | {
        "type": {"name": "Gnc.Vector3", "kind": "qualifiedIdentifier"}
    }
    with pytest.raises(ValueError, match=rf"{channel['name']}.*Gnc\.Vector3"):
        decoders(dictionary)

    dictionary["telemetryChannels"][1] = channel | {"type": {"name": "F32", "kind": "float"}}
    assert decoders(dictionary)[channel["id"]][1](struct.pack(">f", 0.5)) == 0.5
