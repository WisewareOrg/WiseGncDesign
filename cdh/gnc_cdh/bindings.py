"""The data dictionary: for each hosted algorithm, its class, its sample type, and which input
role and signal feeds each sample field and which state field feeds each output role and
signal, in neutral names.

Input signals name physical quantities; output signals name the state quantity they carry.
Signals and their frames are listed in `cdh/README.md`.
"""

from collections.abc import Mapping
from types import MappingProxyType

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample
from gnc_cdh.algorithm_binding import AlgorithmBinding
from gnc_cdh.input_signal import InputSignal
from gnc_cdh.output_signal import OutputSignal

__all__ = ["BINDINGS", "binding"]


BINDINGS: Mapping[str, AlgorithmBinding] = MappingProxyType(
    {
        "imu_dead_reckoning": AlgorithmBinding(
            algorithm=ImuDeadReckoner,
            sample_type=ImuSample,
            inputs=(
                InputSignal("imu", "angular_rate", "omega_B", frame="platform_to_body"),
                InputSignal("imu", "specific_force", "accel_B", frame="platform_to_body"),
            ),
            outputs=(
                OutputSignal("navigation", "sigma_BN", "sigma_BN"),
                OutputSignal("navigation", "r_N", "r_N"),
                OutputSignal("navigation", "v_N", "v_N"),
            ),
        ),
    }
)
"""Every hosted algorithm's binding, by name."""


def binding(name: str) -> AlgorithmBinding:
    """The binding registered as `name`.

    Raises:
        ValueError: naming `name` and every registered name.
    """
    try:
        return BINDINGS[name]
    except KeyError:
        raise ValueError(f"no algorithm {name!r}; known: {sorted(BINDINGS)}") from None
