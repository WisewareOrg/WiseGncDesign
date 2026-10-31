"""C&DH partition for the Basilisk host: marshals cdh.bindings' data dictionary to and from
Basilisk messages, and builds a named algorithm's host module from a scenario's own input
readers, initial-state callable and algorithm parameters."""

from collections.abc import Callable
from typing import Any

import numpy as np

from cdh.basilisk.algorithm_module import AlgorithmModule, FieldMap
from cdh.basilisk.signals import FRAMES, SIGNALS
from cdh.bindings import BINDINGS


def make_fsw(
    name: str,
    inputs: dict[str, Any],
    initial_state: Callable[[], dict],
    mountings: dict[str, np.ndarray] | None = None,
    **params: Any,
) -> AlgorithmModule:
    """Looks up the named algorithm's data dictionary, resolves it against the Basilisk
    signals table into `AlgorithmModule`'s field maps and fresh output messages, and builds the
    module with the caller's input readers. Passes `params` (e.g. `mu`) through to the
    algorithm's construction alongside whatever `initial_state()` returns."""
    binding = BINDINGS[name]

    input_map = []
    resolved_mountings: dict[str, np.ndarray] = {}
    for role, sample_fields in binding.inputs.items():
        for sample_field, (signal, frame) in sample_fields.items():
            _reader_type, payload_field = SIGNALS[(role, signal)]
            input_map.append(
                FieldMap(f"{role}.{payload_field}", sample_field, frame=FRAMES.get(frame))
            )
            if frame is not None:
                resolved_mountings.setdefault(role, np.eye(3))

    output_map = []
    outputs: dict[str, tuple[type, Any]] = {}
    for role, state_attrs in binding.outputs.items():
        for state_attr, signal in state_attrs.items():
            (payload_type, message_type), payload_field = SIGNALS[(role, signal)]
            if role not in outputs:
                outputs[role] = (payload_type, message_type())
            output_map.append(FieldMap(state_attr, f"{role}.{payload_field}"))

    return AlgorithmModule(
        inputs=inputs,
        outputs=outputs,
        input_map=input_map,
        output_map=output_map,
        sample_type=binding.sample_type,
        make_algorithm=binding.make_algorithm,
        init_from=lambda: {**initial_state(), **params},
        mountings=mountings if mountings is not None else resolved_mountings,
    )
