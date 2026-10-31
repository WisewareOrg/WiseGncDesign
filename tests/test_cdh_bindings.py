"""Pins cdh.bindings' data dictionary against the Basilisk transport's signals table, so a typo
in either resolves to the wrong Basilisk field instead of silently matching."""

from Basilisk.architecture import messaging

from cdh.basilisk.signals import SIGNALS
from cdh.bindings import BINDINGS


def test_imu_dead_reckoning_inputs_resolve_to_the_expected_basilisk_fields():
    binding = BINDINGS["imu_dead_reckoning"]
    for role, sample_fields in binding.inputs.items():
        for _sample_field, (signal, _frame) in sample_fields.items():
            assert SIGNALS[(role, signal)][0] is messaging.IMUSensorMsgReader

    assert SIGNALS[("imu", "angular_rate")] == (messaging.IMUSensorMsgReader, "AngVelPlatform")
    assert SIGNALS[("imu", "specific_force")] == (messaging.IMUSensorMsgReader, "AccelPlatform")


def test_imu_dead_reckoning_outputs_resolve_to_the_expected_basilisk_fields():
    assert SIGNALS[("nav_att", "sigma_BN")] == (
        (messaging.NavAttMsgPayload, messaging.NavAttMsg),
        "sigma_BN",
    )
    assert SIGNALS[("nav_trans", "r_N")] == (
        (messaging.NavTransMsgPayload, messaging.NavTransMsg),
        "r_BN_N",
    )
    assert SIGNALS[("nav_trans", "v_N")] == (
        (messaging.NavTransMsgPayload, messaging.NavTransMsg),
        "v_BN_N",
    )


def test_every_neutral_signal_in_the_dictionary_has_a_basilisk_resolution():
    binding = BINDINGS["imu_dead_reckoning"]

    for role, sample_fields in binding.inputs.items():
        for _sample_field, (signal, _frame) in sample_fields.items():
            assert (role, signal) in SIGNALS, f"no Basilisk resolution for ({role!r}, {signal!r})"

    for role, state_attrs in binding.outputs.items():
        for _state_attr, signal in state_attrs.items():
            assert (role, signal) in SIGNALS, f"no Basilisk resolution for ({role!r}, {signal!r})"
