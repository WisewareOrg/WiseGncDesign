"""Builds a named algorithm's Basilisk host module from the data dictionary and the caller's
readers."""

import functools
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from gnc_cdh.basilisk.algorithm_module import AlgorithmModule
from gnc_cdh.basilisk.input_map import InputMap
from gnc_cdh.basilisk.output_map import OutputMap
from gnc_cdh.basilisk.signals import INPUT_SIGNALS, OUTPUT_SIGNALS
from gnc_cdh.bindings import binding
from gnc_cdh.frames import TRANSFORMS

__all__ = ["make_fsw"]


def _mounting(role: str, dcm: Any) -> np.ndarray:
    array = np.array(dcm, dtype=float)
    if (
        array.shape != (3, 3)
        or not np.allclose(array @ array.T, np.eye(3), atol=1e-9)
        or not np.isclose(np.linalg.det(array), 1.0, atol=1e-9)
    ):
        raise ValueError(f"mounting for {role!r} is not a proper rotation (3, 3) DCM: {dcm!r}")
    array.setflags(write=False)
    return array


def make_fsw(
    name: str,
    inputs: Mapping[str, Any],
    initial_state: Callable[[], Mapping[str, Any]],
    mountings: Mapping[str, np.ndarray] | None = None,
    **params: Any,
) -> AlgorithmModule:
    """Builds the `AlgorithmModule` hosting the algorithm registered as `name`.

    Args:
        name: a key of `gnc_cdh.bindings.BINDINGS`.
        inputs: reader by input role, each subscribed by the caller; roles the algorithm reads
            no signal from are left out of the module.
        initial_state: returns the algorithm's initial state by constructor parameter name,
            called at each `Reset`; keys naming no parameter are left out.
        mountings: the DCM [PB] by input role, v_P = [PB] v_B, for every role carrying a
            signal with a frame; the transform is `gnc_cdh.frames.platform_to_body`.
        **params: further constructor parameters, e.g. `mu` (m^3/s^2).

    Returns:
        The module, with one output message per Basilisk message the outputs resolve to, by
        message name (`AlgorithmModule.output_messages`).

    Raises:
        ValueError: when `name` is unknown; an input role is absent from `inputs` or its reader
            has the wrong type; a (role, signal) has no Basilisk resolution; a framed role has no
            mounting, a mounting names a role without a frame, or a mounting is not a (3, 3)
            proper rotation (orthonormal, determinant +1); or a key of `params` names no
            constructor parameter. At `Reset`, when `initial_state()` and `params` share a key
            or together miss a required parameter.
    """
    algorithm_binding = binding(name)
    mountings = dict(mountings or {})

    framed_roles = {s.role for s in algorithm_binding.inputs if s.frame is not None}
    stray = sorted(set(mountings) - framed_roles)
    if stray:
        raise ValueError(f"mountings for {stray} name no input role with a frame")
    unmounted = sorted(framed_roles - set(mountings))
    if unmounted:
        raise ValueError(f"input roles {unmounted} need a mounting [PB] in mountings")
    resolved_mountings = {role: _mounting(role, dcm) for role, dcm in mountings.items()}

    unknown_params = sorted(set(params) - set(algorithm_binding.init_parameters))
    if unknown_params:
        raise ValueError(f"params {unknown_params} name no parameter of {name!r}")

    readers: dict[str, Any] = {}
    input_maps = []
    for signal in algorithm_binding.inputs:
        resolved = INPUT_SIGNALS.get((signal.role, signal.signal))
        if resolved is None:
            raise ValueError(f"no Basilisk input for {(signal.role, signal.signal)}")
        if signal.role not in inputs:
            raise ValueError(f"inputs has no role {signal.role!r}; {name!r} reads it")
        if not isinstance(inputs[signal.role], resolved.reader_type):
            raise ValueError(
                f"input {signal.role!r} is a {type(inputs[signal.role]).__name__}, expected "
                f"{resolved.reader_type.__name__}"
            )
        readers[signal.role] = inputs[signal.role]
        transform = (
            None
            if signal.frame is None
            else functools.partial(TRANSFORMS[signal.frame], resolved_mountings[signal.role])
        )
        input_maps.append(
            InputMap(signal.role, resolved.payload_field, signal.sample_field, transform)
        )

    messages: dict[str, Any] = {}
    output_maps = []
    for signal in algorithm_binding.outputs:
        resolved = OUTPUT_SIGNALS.get((signal.role, signal.signal))
        if resolved is None:
            raise ValueError(f"no Basilisk output for {(signal.role, signal.signal)}")
        if resolved.message not in messages:
            messages[resolved.message] = resolved.message_type()
        output_maps.append(OutputMap(signal.state_field, resolved.message, resolved.payload_field))

    def init_from() -> dict[str, Any]:
        state = dict(initial_state())
        shared = sorted(set(state) & set(params))
        if shared:
            raise ValueError(f"initial_state() and params both supply {shared}")
        return {**state, **params}

    return AlgorithmModule(
        inputs=readers,
        outputs=messages,
        input_maps=input_maps,
        output_maps=output_maps,
        sample_type=algorithm_binding.sample_type,
        make_algorithm=algorithm_binding.build,
        init_from=init_from,
    )
