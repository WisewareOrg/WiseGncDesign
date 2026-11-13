"""The F´ host on the link, and its refusals, against messages written by hand.

Skipped without the deployment `just fsw` builds.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from Basilisk.architecture import messaging
from scipy.spatial.transform import Rotation

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner
from gnc_cdh.fprime import DICTIONARY, FprimeModule

pytest.importorskip("gnc_cdh.fprime._wise_fsw", reason="the F´ build is absent; run `just fsw`")

REPOSITORY = Path(__file__).parents[3]

ONE_SECOND_NS = 1_000_000_000

MU = 3.986004360e14
"""m^3/s^2, Earth's gravitational parameter, as the scenarios set it."""

STATE = {
    "epoch": 0.0,
    "attitude": [1.0, 0.0, 0.0, 0.0],
    "position": [6871.0e3, 0.0, 0.0],
    "velocity": [0.0, 5.4e3, 5.4e3],
}
"""`nav.initNavState`'s arguments: a state at t = 0."""


def _module() -> FprimeModule:
    """A host on an unsubscribed IMU reader, mounted at identity.

    Returns:
        The `FprimeModule`.
    """
    return FprimeModule(messaging.IMUSensorMsgReader(), mu=MU, dcm_PB=np.eye(3))


def test_reset_refuses_an_unsubscribed_imu_and_keeps_the_exception():
    """`Reset` names the IMU reader that no message feeds, the exception kept in `failure`."""
    module = _module()

    with pytest.raises(RuntimeError, match="IMU reader is not subscribed") as raised:
        module.Reset(0)

    assert module.failure is raised.value


def test_a_tick_refuses_an_imu_never_written_and_keeps_the_exception():
    """A tick after the reset names the IMU message never written, the exception kept."""
    module = _module()
    imu = messaging.IMUSensorMsg()
    module._imu.subscribeTo(imu)
    module.Reset(0)

    with pytest.raises(RuntimeError, match=r"IMU has not been written at t = 1.0 s") as raised:
        module.UpdateState(ONE_SECOND_NS)

    assert module.failure is raised.value


def test_the_link_carries_a_command_up_and_its_response_and_every_write_down():
    """A command runs at the next tick, answered with no reason; each write comes down decoded.

    The handler writes `navState` alone, before the step writes it with the estimate, both tagged
    with the tick's time.
    """
    module = _module()
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)

    module.uplink(module.dictionary.encode_command("nav.initNavState", STATE), 5)
    assert module.responses() == []
    module.UpdateState(ONE_SECOND_NS)
    writes = module.telemetry()

    assert module.responses() == [(5, module.dictionary.responses["OK"], None)]
    assert module.failure is None
    channels = module.dictionary.channels_by_id
    assert [(channels[i].name, t) for i, t, _ in writes] == [
        ("nav.navState", ONE_SECOND_NS),
        ("nav.navState", ONE_SECOND_NS),
        ("nav.bodyEciPos", ONE_SECOND_NS),
        ("nav.bodyEciVel", ONE_SECOND_NS),
        ("nav.bodyEciAttitude", ONE_SECOND_NS),
    ]
    nav_state = module.dictionary.channel("nav.navState")
    payloads = [value for i, _, value in writes if i == nav_state.id]
    assert module.values(nav_state, payloads).tolist() == ["initialized", "propagated"]
    attitude = module.dictionary.channel("nav.bodyEciAttitude")
    payloads = [value for i, _, value in writes if i == attitude.id]
    np.testing.assert_array_equal(module.values(attitude, payloads), [STATE["attitude"]])
    assert module.telemetry() == []


def test_the_host_mounts_the_imu_as_it_is_given():
    """On a mounting that is not the identity, the host's estimate is the notebook's.

    Ten readings are enough for a transposed mounting to show far above rounding.
    """
    mounting = Rotation.from_euler("zyx", [10.0, -20.0, 30.0], degrees=True).as_matrix()
    module = FprimeModule(messaging.IMUSensorMsgReader(), mu=MU, dcm_PB=mounting)
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)
    module.uplink(module.dictionary.encode_command("nav.initNavState", STATE), 1)
    python = ImuDeadReckoner(mu=MU, dcm_PB=mounting)
    python.initNavState(**STATE)
    rng = np.random.default_rng(7)

    for k in range(1, 11):
        reading = messaging.IMUSensorMsgPayload()
        reading.AngVelPlatform = (0.02 * rng.normal(size=3)).tolist()
        reading.AccelPlatform = (1e-3 * rng.normal(size=3)).tolist()
        imu.write(reading, k * ONE_SECOND_NS, 0)
        module.UpdateState(k * ONE_SECOND_NS)
        python.step(
            t=float(k),
            AngVelPlatform=np.array(reading.AngVelPlatform),
            AccelPlatform=np.array(reading.AccelPlatform),
        )

    channels = module.dictionary.channels_by_id
    latest = {channels[i].name: channels[i].decode(value) for i, _, value in module.telemetry()}
    np.testing.assert_allclose(latest["nav.bodyEciAttitude"], python.q_BN, rtol=0, atol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciPos"], python.r_BN_N, rtol=1e-12)
    np.testing.assert_allclose(latest["nav.bodyEciVel"], python.v_BN_N, rtol=1e-12)


def test_a_command_f_prime_rejects_is_answered_with_its_response_and_fails_nothing():
    """A packet with an opcode no instance has is answered `INVALID_OPCODE`, with no reason."""
    module = _module()
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)
    packet = module.dictionary.encode_command("nav.initNavState", STATE)
    unknown = max(c["opcode"] for c in json.loads(DICTIONARY.read_text())["commands"]) + 1

    module.uplink(packet[:2] + unknown.to_bytes(4, "big") + packet[6:], 9)
    module.UpdateState(ONE_SECOND_NS)

    assert module.responses() == [(9, module.dictionary.responses["INVALID_OPCODE"], None)]
    assert module.failure is None


def test_a_host_without_the_f_prime_build_says_to_build_it(monkeypatch: pytest.MonkeyPatch):
    """With no extension to import, building a host names the recipe that builds it.

    Args:
        monkeypatch: hides the extension from the import system.
    """
    monkeypatch.setitem(sys.modules, "gnc_cdh.fprime._wise_fsw", None)

    with pytest.raises(ModuleNotFoundError, match="not built; run `just fsw`"):
        _module()


def test_a_host_refuses_an_extension_rebuilt_after_the_process_loaded_it(
    monkeypatch: pytest.MonkeyPatch,
):
    """Once the extension changes on disk, building or resetting a host says restart the kernel.

    Args:
        monkeypatch: records a different file as the one this process loaded.
    """
    built_before = _module()
    monkeypatch.setattr("gnc_cdh.fprime.module._loaded_stamp", (-1, -1))

    with pytest.raises(RuntimeError, match="rebuilt after this process loaded it.*restart"):
        _module()
    with pytest.raises(RuntimeError, match="rebuilt after this process loaded it.*restart"):
        built_before.Reset(0)


@pytest.mark.parametrize("excess_ns", [1, 500, 999])
def test_a_tick_that_is_not_a_whole_microsecond_is_refused_naming_its_time(excess_ns: int):
    """A tick at a whole microsecond is stepped; one nanoseconds past it raises, naming its time.

    Args:
        excess_ns: ns past a whole microsecond.
    """
    module = _module()
    imu = messaging.IMUSensorMsg()
    imu.write(messaging.IMUSensorMsgPayload(), 0, 0)
    module._imu.subscribeTo(imu)
    module.Reset(0)
    whole = ONE_SECOND_NS + 1_000
    module.UpdateState(whole)

    with pytest.raises(RuntimeError, match=r"1\.000001|1000001"):
        module.UpdateState(whole + excess_ns)


def test_the_build_names_the_pinned_framework_tag_and_the_project_version():
    """`build` is the host, the F´ tag the justfile pins and the dictionary's project version."""
    build = _module().build

    tag = subprocess.run(
        ["just", "--evaluate", "fprime_tag"], cwd=REPOSITORY, capture_output=True, text=True
    ).stdout.strip()
    assert set(build) == {"host", "frameworkVersion", "projectVersion"}
    assert build["host"] == "gnc_cdh.fprime.FprimeModule"
    assert build["frameworkVersion"] == tag
    assert tag
    assert isinstance(build["projectVersion"], str)
    assert build["projectVersion"]
