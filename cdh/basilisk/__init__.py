"""C&DH partition for the Basilisk host: marshals cdh.bindings' data dictionary to and from
Basilisk messages, and builds a named algorithm's host module from a scenario's own input
readers, initial-state callable and algorithm parameters."""

from collections.abc import Callable
from typing import Any

import numpy as np

from cdh.basilisk.algorithm_module import AlgorithmModule
from cdh.basilisk.bindings import IMU_DEAD_RECKONING_BINDING

_BINDINGS = {"imu_dead_reckoning": IMU_DEAD_RECKONING_BINDING}


def make_fsw(
    name: str,
    inputs: dict[str, Any],
    initial_state: Callable[[], dict],
    mountings: dict[str, np.ndarray] | None = None,
    **params: Any,
) -> AlgorithmModule:
    """Looks up the named algorithm's binding, builds its `AlgorithmModule` with the caller's
    input readers, and passes `params` (e.g. `mu`) through to the algorithm's construction
    alongside whatever `initial_state()` returns."""
    binding = _BINDINGS[name]
    return AlgorithmModule(
        inputs=inputs,
        outputs=binding.make_outputs(),
        input_map=binding.input_map,
        output_map=binding.output_map,
        sample_type=binding.sample_type,
        make_algorithm=binding.make_algorithm,
        init_from=lambda: {**initial_state(), **params},
        mountings=mountings if mountings is not None else binding.mountings,
    )
