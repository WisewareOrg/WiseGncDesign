"""The data dictionary: every binding resolves against the Basilisk transport, and
`AlgorithmBinding` derives and validates what it states."""

from dataclasses import dataclass

import numpy as np
import pytest

from gnc_cdh import BINDINGS, AlgorithmBinding, InputSignal
from gnc_cdh.basilisk import make_fsw
from gnc_cdh.basilisk.signals import INPUT_SIGNALS


@pytest.mark.parametrize("name", sorted(BINDINGS))
def test_every_binding_builds_against_real_basilisk_readers(name):
    algorithm_binding = BINDINGS[name]
    roles = {s.role for s in algorithm_binding.inputs}
    readers = {
        s.role: INPUT_SIGNALS[(s.role, s.signal)].reader_type() for s in algorithm_binding.inputs
    }
    mountings = {s.role: np.eye(3) for s in algorithm_binding.inputs if s.frame is not None}

    module = make_fsw(name, inputs=readers, initial_state=dict, mountings=mountings)

    assert {m.input for m in module.input_maps} == roles
    assert {m.state_field for m in module.output_maps} == {
        s.state_field for s in algorithm_binding.outputs
    }


def test_init_keys_are_the_required_constructor_parameters_other_than_t0():
    assert BINDINGS["imu_dead_reckoning"].init_keys == ("sigma0_BN", "r0_N", "v0_N", "mu")


@dataclass(frozen=True)
class _Sample:
    """A sample with one input field, `x`."""

    t: float
    x: np.ndarray


class _Algorithm:
    """An algorithm with one required parameter, `gain`, and one defaulted, `offset`."""

    def __init__(self, gain: float, t0: float, offset: float = 0.0) -> None:
        self.gain, self.t0, self.offset = gain, t0, offset


def test_a_defaulted_parameter_is_optional_and_accepted():
    algorithm_binding = AlgorithmBinding(_Algorithm, _Sample, (InputSignal("r", "s", "x"),), ())

    assert algorithm_binding.init_keys == ("gain",)
    built = algorithm_binding.build(2.0, {"gain": 3.0})
    assert (built.t0, built.gain, built.offset) == (2.0, 3.0, 0.0)
    assert algorithm_binding.build(2.0, {"gain": 3.0, "offset": 1.0}).offset == 1.0


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ((_Algorithm, dict, (), ()), "not a dataclass with field 't'"),
        ((_Algorithm, _Sample, (InputSignal("r", "s", "x", frame="sideways"),), ()), "'sideways'"),
        ((lambda gain: None, _Sample, (), ()), "takes no 't0'"),
    ],
)
def test_construction_rejects_an_inconsistent_binding(arguments, message):
    with pytest.raises(ValueError, match=message):
        AlgorithmBinding(*arguments)
