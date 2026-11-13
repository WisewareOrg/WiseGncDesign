"""The F´ host's refusals and its run-file datasets, against messages written by hand.

Needs the deployment `just fsw` builds.
"""

import functools
import json
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest
from Basilisk.architecture import messaging
from scipy.spatial.transform import Rotation
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from gnc_algorithms.imu_dead_reckoning import dead_reckoner
from gnc_cdh.basilisk import UNITS
from gnc_cdh.fprime import DICTIONARY, FprimeModule, decoders

REPOSITORY = Path(__file__).parents[3]

ONE_SECOND_NS = 1_000_000_000

MOUNTING = Rotation.from_euler("zyx", [10.0, -20.0, 30.0], degrees=True).as_matrix()
"""A mounting [PB] that is not the identity, so a transposed mounting shows."""

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

    The truth is equal, the `est/*` names equal with the units of `UNITS`, [NB] to 1e-12 and the
    position and velocity to a relative 1e-12.
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
    assert {"est/sigma_BN", "est/r_BN_N", "est/v_BN_N"} <= set(names)
    for name in names:
        assert python[name][1] == fprime[name][1] == UNITS[name.removeprefix("est/")]
    attitude = [Rotation.from_mrp(d["est/sigma_BN"][0]).as_matrix() for d in (python, fprime)]
    np.testing.assert_allclose(attitude[1], attitude[0], rtol=0, atol=1e-12)
    for name in ("est/r_BN_N", "est/v_BN_N"):
        np.testing.assert_allclose(fprime[name][0], python[name][0], rtol=1e-12)
