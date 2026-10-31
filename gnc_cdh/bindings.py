"""The C&DH partition's data dictionary: for each algorithm, which neutral input role and
signal feeds which of its sample fields, and which of its state fields feeds which neutral
output role and signal, entirely in this file's own vocabulary. Each transport under
`gnc_cdh/<transport>/` resolves these signals against its own wire format;
`scripts/check-cdh-dictionary-neutral.sh` keeps this file's vocabulary to itself."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample


@dataclass(frozen=True)
class AlgorithmBinding:
    """Everything transport-independent about hosting one algorithm: how to build it, and its
    data dictionary. `inputs` is `{role: {sample_field: (signal, frame)}}`, `frame` naming a
    transform the transport applies before the value reaches the algorithm (`None` names the
    identity transform). `outputs` is `{role: {state_attr: signal}}`. `init_keys` names the keys
    `initial_state()` must supply to `make_algorithm`, on top of a host's own parameters."""

    sample_type: type
    make_algorithm: Callable[[float, dict], Any]
    inputs: dict[str, dict[str, tuple[str, str | None]]]
    outputs: dict[str, dict[str, str]]
    init_keys: tuple[str, ...]


BINDINGS: dict[str, AlgorithmBinding] = {
    "imu_dead_reckoning": AlgorithmBinding(
        sample_type=ImuSample,
        make_algorithm=lambda t0, init: ImuDeadReckoner(
            init["sigma0_BN"], init["r0_N"], init["v0_N"], t0, init["mu"]
        ),
        inputs={
            "imu": {
                "omega_B": ("angular_rate", "platform_to_body"),
                "accel_B": ("specific_force", "platform_to_body"),
            },
        },
        outputs={
            "nav_att": {"sigma_BN": "sigma_BN"},
            "nav_trans": {"r_N": "r_N", "v_N": "v_N"},
        },
        init_keys=("sigma0_BN", "r0_N", "v0_N"),
    ),
}
