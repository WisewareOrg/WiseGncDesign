"""The F´ host on the link, and its refusals, against messages written by hand.

Skipped without the deployment `just fsw` builds.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from Basilisk.architecture import messaging

from gnc_cdh.fprime import FprimeModule

pytest.importorskip("gnc_cdh.fprime._wise_fsw", reason="the F´ build is absent; run `just fsw`")

REPOSITORY = Path(__file__).parents[3]

ONE_SECOND_NS = 1_000_000_000


def _module() -> FprimeModule:
    """A host on an unsubscribed IMU reader, mounted at identity.

    Returns:
        The `FprimeModule`.
    """
    return FprimeModule(messaging.IMUSensorMsgReader(), mu=3.986004360e14, dcm_PB=np.eye(3))


@pytest.fixture
def imu() -> messaging.IMUSensorMsg:
    """An IMU message written once with a zero reading, alive for the test.

    Returns:
        The message.
    """
    message = messaging.IMUSensorMsg()
    message.write(messaging.IMUSensorMsgPayload(), 0, 0)
    return message


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


def test_the_link_carries_a_command_up_and_its_response_and_every_write_down(
    imu: messaging.IMUSensorMsg,
):
    """A command runs at the next tick, answered with no reason; each write comes down decoded.

    The handler writes `navState` alone, before the step writes it with the estimate, both tagged
    with the tick's time.

    Args:
        imu: the IMU message the host reads.
    """
    module = _module()
    module._imu.subscribeTo(imu)
    module.Reset(0)
    state = {
        "epoch": 0.0,
        "attitude": [1.0, 0.0, 0.0, 0.0],
        "position": [6871.0e3, 0.0, 0.0],
        "velocity": [0.0, 5.4e3, 5.4e3],
    }

    module.uplink(module.dictionary.encode_command("nav.initNavState", state), 5)
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
    assert module.telemetry() == []


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

    The reset's exception is kept in `failure`.

    Args:
        monkeypatch: records a different file as the one this process loaded.
    """
    built_before = _module()
    monkeypatch.setattr("gnc_cdh.fprime.module._loaded_stamp", (-1, -1))

    with pytest.raises(RuntimeError, match="rebuilt after this process loaded it.*restart"):
        _module()
    with pytest.raises(
        RuntimeError, match="rebuilt after this process loaded it.*restart"
    ) as raised:
        built_before.Reset(0)
    assert built_before.failure is raised.value


@pytest.mark.parametrize("excess_ns", [1, 500, 999])
def test_a_tick_that_is_not_a_whole_microsecond_is_refused_naming_its_time(
    excess_ns: int, imu: messaging.IMUSensorMsg
):
    """A tick at a whole microsecond is stepped; one nanoseconds past it raises, naming its time.

    The exception is kept in `failure`.

    Args:
        excess_ns: ns past a whole microsecond.
        imu: the IMU message the host reads.
    """
    module = _module()
    module._imu.subscribeTo(imu)
    module.Reset(0)
    whole = ONE_SECOND_NS + 1_000
    module.UpdateState(whole)

    with pytest.raises(RuntimeError, match=r"1\.000001|1000001") as raised:
        module.UpdateState(whole + excess_ns)
    assert module.failure is raised.value


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
