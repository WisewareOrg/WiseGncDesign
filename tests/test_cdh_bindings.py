"""Pins gnc_cdh.bindings' data dictionary against the Basilisk transport's signals table: every
registered algorithm's entries resolve, and the imu_dead_reckoning entries resolve to their
exact expected Basilisk fields and frame."""

from Basilisk.architecture import messaging

from gnc_cdh.basilisk.signals import FRAMES, SIGNALS
from gnc_cdh.bindings import BINDINGS

_EXPECTED_INPUT_SIGNALS = {
    ("imu", "angular_rate"): (messaging.IMUSensorMsgReader, "AngVelPlatform"),
    ("imu", "specific_force"): (messaging.IMUSensorMsgReader, "AccelPlatform"),
}
_EXPECTED_OUTPUT_SIGNALS = {
    ("nav_att", "sigma_BN"): ((messaging.NavAttMsgPayload, messaging.NavAttMsg), "sigma_BN"),
    ("nav_trans", "r_N"): ((messaging.NavTransMsgPayload, messaging.NavTransMsg), "r_BN_N"),
    ("nav_trans", "v_N"): ((messaging.NavTransMsgPayload, messaging.NavTransMsg), "v_BN_N"),
}
_EXPECTED_FRAMES = {"platform_to_body": "P->B"}


def test_every_registered_algorithm_resolves_against_the_signals_table():
    # Scales with the registry: a second algorithm added to BINDINGS is covered here without
    # changing this test, unlike a test that names one algorithm's binding directly.
    for binding in BINDINGS.values():
        for role, sample_fields in binding.inputs.items():
            for _sample_field, (signal, frame) in sample_fields.items():
                assert (role, signal) in SIGNALS, f"no Basilisk resolution for {(role, signal)}"
                if frame is not None:
                    assert frame in FRAMES, f"no frame translation for {frame!r}"
        for role, state_attrs in binding.outputs.items():
            for _state_attr, signal in state_attrs.items():
                assert (role, signal) in SIGNALS, f"no Basilisk resolution for {(role, signal)}"


def test_imu_dead_reckoning_inputs_resolve_to_their_exact_basilisk_field_and_frame():
    binding = BINDINGS["imu_dead_reckoning"]
    seen = set()
    for role, sample_fields in binding.inputs.items():
        for _sample_field, (signal, frame) in sample_fields.items():
            seen.add((role, signal))
            assert SIGNALS[(role, signal)] == _EXPECTED_INPUT_SIGNALS[(role, signal)]
            assert FRAMES[frame] == _EXPECTED_FRAMES[frame]
    assert seen == set(_EXPECTED_INPUT_SIGNALS)


def test_imu_dead_reckoning_outputs_resolve_to_their_exact_basilisk_field():
    binding = BINDINGS["imu_dead_reckoning"]
    seen = set()
    for role, state_attrs in binding.outputs.items():
        for _state_attr, signal in state_attrs.items():
            seen.add((role, signal))
            assert SIGNALS[(role, signal)] == _EXPECTED_OUTPUT_SIGNALS[(role, signal)]
    assert seen == set(_EXPECTED_OUTPUT_SIGNALS)
