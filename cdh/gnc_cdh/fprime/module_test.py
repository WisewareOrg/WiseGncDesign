"""The F´ host's refusals and its run-file datasets, against messages written by hand.

Skipped without the deployment `just fsw` builds.
"""

import functools
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from Basilisk.architecture import messaging
from scipy.spatial.transform import Rotation
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from gnc_algorithms.imu_dead_reckoning import dead_reckoner
from gnc_cdh import UNITS
from gnc_cdh.fprime import FprimeModule

pytest.importorskip("gnc_cdh.fprime._wise_fsw", reason="the F´ build is absent; run `just fsw`")

REPOSITORY = Path(__file__).parents[3]

ONE_SECOND_NS = 1_000_000_000

MOUNTING = Rotation.from_euler("zyx", [10.0, -20.0, 30.0], degrees=True).as_matrix()
"""A mounting [PB] that is not the identity, so a transposed mounting shows."""

INITIAL = {
    "q0_BN": Rotation.from_euler("zyx", [40.0, -25.0, 60.0], degrees=True).as_quat(
        scalar_first=True
    ),
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

    assert sorted(datasets) == ["est/q_BN", "est/r_BN_N", "est/v_BN_N"]
    np.testing.assert_array_equal(datasets["est/q_BN"][0][0], INITIAL["q0_BN"])
    np.testing.assert_array_equal(datasets["est/r_BN_N"][0][0], INITIAL["r0_N"])
    assert datasets["est/r_BN_N"][1] == "m"
    positions = datasets["est/r_BN_N"][0]
    assert len({tuple(row) for row in positions}) == len(positions)
    with pytest.raises(KeyError, match="no telemetry was logged at t = 0.25 s"):
        module.estimate_datasets(np.array([0.25]))


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


def _flown(host: str) -> dict:
    """Fly a fresh nominal `Leo500` for 60 s through the host's `fly`, mounted at `MOUNTING`.

    Args:
        host: "python" for the dead reckoner's `AlgorithmModule`, "fprime" for `FprimeModule`.

    Returns:
        The datasets the host's `fly` returns.
    """
    scenario = Leo500()
    scenario.vehicle.imu.dcm_PB = MOUNTING
    if host == "python":
        fsw = dead_reckoner(scenario)
    else:
        fsw = FprimeModule(
            scenario.vehicle.readers()["imu"],
            mu=scenario.mu_m3_s2["earth"],
            dcm_PB=MOUNTING,
            initial=scenario.initial_state(),
        )
    return fsw.fly(functools.partial(scenario.run, duration_s=60.0))


def test_both_hosts_record_the_same_truth_est_names_units_and_estimate():
    """Flown on one mounting and one scenario, the hosts' run-file datasets agree.

    The truth is equal, the `est/*` names equal with the units of `UNITS`, the quaternion to 1e-12
    and the position and velocity to a relative 1e-12.
    """
    python, fprime = _flown("python"), _flown("fprime")

    truth = sorted(name for name in python if name.startswith("truth/"))
    assert truth
    assert truth == sorted(name for name in fprime if name.startswith("truth/"))
    for name in truth:
        np.testing.assert_array_equal(python[name][0], fprime[name][0])
        assert python[name][1] == fprime[name][1]
    names = sorted(name for name in python if name.startswith("est/"))
    assert names == sorted(name for name in fprime if name.startswith("est/"))
    assert {"est/q_BN", "est/r_BN_N", "est/v_BN_N"} <= set(names)
    for name in names:
        assert python[name][1] == fprime[name][1] == UNITS[name.removeprefix("est/")]
    np.testing.assert_allclose(fprime["est/q_BN"][0], python["est/q_BN"][0], rtol=0, atol=1e-12)
    for name in ("est/r_BN_N", "est/v_BN_N"):
        np.testing.assert_allclose(fprime[name][0], python[name][0], rtol=1e-12)
