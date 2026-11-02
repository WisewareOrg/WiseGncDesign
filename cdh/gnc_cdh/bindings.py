"""The data dictionary: for each hosted algorithm, its class, its sample type, and which input
role and signal feeds each sample field and which state field feeds each output role and
signal, in neutral names.

Input signals name physical quantities; output signals name the state quantity they carry.
Signals and their frames are listed in `cdh/README.md`.
"""

import dataclasses
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from gnc_algorithms.imu_dead_reckoning import ImuDeadReckoner, ImuSample
from gnc_cdh.frames import TRANSFORMS
from gnc_cdh.hosted import HostedAlgorithm

__all__ = ["BINDINGS", "AlgorithmBinding", "InputSignal", "OutputSignal", "binding"]

_TIME_PARAMETER = "t0"


@dataclass(frozen=True)
class InputSignal:
    """One sample field, fed from one signal of one input role.

    Attributes:
        role: the input port, e.g. one sensor.
        signal: the neutral quantity read from that role.
        sample_field: the field of the algorithm's sample type that receives it.
        frame: the name of a transform in `gnc_cdh.frames.TRANSFORMS` the host applies with
            that role's mounting, or `None` for the value as read.
    """

    role: str
    signal: str
    sample_field: str
    frame: str | None = None


@dataclass(frozen=True)
class OutputSignal:
    """One state field, published as one signal of one output role.

    Attributes:
        role: the output port.
        signal: the neutral quantity published on that role.
        state_field: the attribute of the algorithm's state that supplies it.
    """

    role: str
    signal: str
    state_field: str


@dataclass(frozen=True)
class AlgorithmBinding:
    """Everything transport-neutral about hosting one algorithm.

    Attributes:
        algorithm: the algorithm class, constructed as `algorithm(t0=..., **init)`.
        sample_type: a dataclass with field `t` (s) and one field per input signal.
        inputs: every sample field other than `t`, each fed by one input signal.
        outputs: every published state field.

    Raises:
        ValueError: at construction, when `sample_type` is not a dataclass with field `t`, a
            frame names no transform in `TRANSFORMS`, or `algorithm` takes no `t0`.
    """

    algorithm: Callable[..., HostedAlgorithm]
    sample_type: type
    inputs: tuple[InputSignal, ...]
    outputs: tuple[OutputSignal, ...]

    def __post_init__(self) -> None:
        if not dataclasses.is_dataclass(self.sample_type) or "t" not in {
            f.name for f in dataclasses.fields(self.sample_type)
        }:
            raise ValueError(f"sample type {self.sample_type!r} is not a dataclass with field 't'")
        for signal in self.inputs:
            if signal.frame is not None and signal.frame not in TRANSFORMS:
                raise ValueError(
                    f"{signal} names frame {signal.frame!r}; known frames: {sorted(TRANSFORMS)}"
                )
        if _TIME_PARAMETER not in inspect.signature(self.algorithm).parameters:
            raise ValueError(f"{self.algorithm!r} takes no {_TIME_PARAMETER!r} parameter")

    @property
    def init_keys(self) -> tuple[str, ...]:
        """The constructor parameters other than `t0` that have no default, which `build`'s
        `init` must supply."""
        return tuple(
            name
            for name, parameter in inspect.signature(self.algorithm).parameters.items()
            if name != _TIME_PARAMETER and parameter.default is inspect.Parameter.empty
        )

    @property
    def init_parameters(self) -> tuple[str, ...]:
        """Every constructor parameter other than `t0`, required or defaulted."""
        return tuple(
            name for name in inspect.signature(self.algorithm).parameters if name != _TIME_PARAMETER
        )

    def build(self, t0: float, init: Mapping[str, Any]) -> HostedAlgorithm:
        """Constructs the algorithm with keyword arguments: `t0` (s), and every constructor
        parameter present in `init`. Keys of `init` that name no parameter are left out.

        Raises:
            ValueError: naming every key of `init_keys` missing from `init`.
        """
        missing = [key for key in self.init_keys if key not in init]
        if missing:
            raise ValueError(f"{self.algorithm.__name__} needs {missing}, missing from init")
        kwargs = {key: init[key] for key in self.init_parameters if key in init}
        return self.algorithm(**{_TIME_PARAMETER: t0}, **kwargs)


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
