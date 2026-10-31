"""Cross-checks cdh.bindings' neutral data dictionary against the Basilisk transport's
resolution of it, so the two cannot silently drift apart."""

import cdh.basilisk.bindings as basilisk_bindings
import cdh.bindings as data_dictionary


def test_basilisk_resolves_every_neutral_input_field():
    neutral = data_dictionary.IMU_DEAD_RECKONING_BINDING
    resolved = basilisk_bindings.IMU_DEAD_RECKONING_BINDING

    expected = {(ib.role, ib.algorithm_field, ib.frame is not None) for ib in neutral.inputs}
    actual = {(fm.src.partition(".")[0], fm.dst, fm.frame is not None) for fm in resolved.input_map}
    assert actual == expected


def test_basilisk_resolves_every_neutral_output_field():
    neutral = data_dictionary.IMU_DEAD_RECKONING_BINDING
    resolved = basilisk_bindings.IMU_DEAD_RECKONING_BINDING

    expected = {(ob.algorithm_field, ob.role) for ob in neutral.outputs}
    actual = {(fm.src, fm.dst.partition(".")[0]) for fm in resolved.output_map}
    assert actual == expected


def test_basilisk_binding_shares_the_neutral_sample_type_and_constructor():
    neutral = data_dictionary.IMU_DEAD_RECKONING_BINDING
    resolved = basilisk_bindings.IMU_DEAD_RECKONING_BINDING

    assert resolved.sample_type is neutral.sample_type
    assert resolved.make_algorithm is neutral.make_algorithm
