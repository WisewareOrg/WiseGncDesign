"""A Basilisk Python `SysModel` hosting one framework-free algorithm, wired by declarative
input and output maps (`InputMap`, `OutputMap`)."""

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from gnc_cdh.basilisk.input_map import InputMap
from gnc_cdh.basilisk.output_map import OutputMap
from gnc_cdh.hosted_algorithm import HostedAlgorithm
from gnc_cdh.hosted_state import HostedState

__all__ = ["PERIOD_S", "AlgorithmModule", "InputMap", "OutputMap"]

_NANOSECONDS_PER_SECOND = 1e9

PERIOD_S = 1.0
"""The flight software's compute period, in s: 1 Hz, whatever the period of the task calling
`UpdateState`."""

_PERIOD_NS = round(PERIOD_S * _NANOSECONDS_PER_SECOND)


class AlgorithmModule(sysModel.SysModel):
    """Hosts one algorithm inside a Basilisk task.

    `Reset` builds the algorithm as `make_algorithm(t0, init_from())`, `t0` being the reset
    time in s, and writes its initial state to every output; a reset counts as a compute. An
    `UpdateState` at least `PERIOD_S` after the last compute reads every input once, builds one
    `sample_type` instance from the input maps with `t` in s, calls `algorithm.step(sample)`, and
    writes the returned state through the output maps. Every other `UpdateState` returns without
    writing, so a task calling it every 0.02 s computes at t = 0 and at each whole second.

    Args:
        inputs: reader by input name, each subscribed by the caller.
        outputs: output message by name.
        input_maps: cover every field of `sample_type` other than `t`, each exactly once.
        output_maps: name only known outputs and their payload fields.
        sample_type: a dataclass with field `t` (s).
        make_algorithm: builds the algorithm from `t0` (s) and the initial-state mapping.
        init_from: returns the initial-state mapping, called at each `Reset`.

    Raises:
        ValueError: at construction, naming the first map that refers to an unknown input,
            output or payload field, or a sample field that is unknown, duplicated or left
            uncovered.
    """

    def __init__(
        self,
        inputs: Mapping[str, Any],
        outputs: Mapping[str, Any],
        input_maps: Sequence[InputMap],
        output_maps: Sequence[OutputMap],
        sample_type: type,
        make_algorithm: Callable[[float, Mapping[str, Any]], HostedAlgorithm],
        init_from: Callable[[], Mapping[str, Any]],
    ) -> None:
        super().__init__()
        self._inputs = MappingProxyType(dict(inputs))
        self._outputs = MappingProxyType(dict(outputs))
        self._input_maps = tuple(input_maps)
        self._output_maps = tuple(output_maps)
        self._sample_type = sample_type
        self._make_algorithm = make_algorithm
        self._init_from = init_from
        self._algorithm: HostedAlgorithm | None = None
        self._computed_ns = 0
        self._validate_maps()

    @property
    def inputs(self) -> Mapping[str, Any]:
        """Reader by input name."""
        return self._inputs

    @property
    def output_messages(self) -> Mapping[str, Any]:
        """Output message by name, the messages this module writes."""
        return self._outputs

    @property
    def input_maps(self) -> tuple[InputMap, ...]:
        """The input maps, in the order given."""
        return self._input_maps

    @property
    def output_maps(self) -> tuple[OutputMap, ...]:
        """The output maps, in the order given."""
        return self._output_maps

    @property
    def algorithm(self) -> HostedAlgorithm:
        """The hosted instance, built by the latest `Reset`, for inspection.

        Raises:
            RuntimeError: before the first `Reset`.
        """
        if self._algorithm is None:
            raise RuntimeError("AlgorithmModule has not been Reset")
        return self._algorithm

    def _validate_maps(self) -> None:
        if not dataclasses.is_dataclass(self._sample_type):
            raise ValueError(f"sample type {self._sample_type!r} is not a dataclass")
        sample_fields = {f.name for f in dataclasses.fields(self._sample_type)}
        if "t" not in sample_fields:
            raise ValueError(f"sample type {self._sample_type.__name__} has no field 't'")

        for m in self._input_maps:
            if m.input not in self._inputs:
                raise ValueError(f"{m} names unknown input {m.input!r}")
            if not hasattr(self._inputs[m.input].zeroMsgPayload, m.payload_field):
                raise ValueError(f"{m} names unknown payload field {m.payload_field!r}")
            if m.sample_field not in sample_fields - {"t"}:
                raise ValueError(
                    f"{m} names unknown field {m.sample_field!r} of {self._sample_type.__name__}"
                )

        mapped = [m.sample_field for m in self._input_maps]
        duplicated = sorted({name for name in mapped if mapped.count(name) > 1})
        if duplicated:
            raise ValueError(f"input maps feed {duplicated} more than once")
        uncovered = sorted(sample_fields - {"t"} - set(mapped))
        if uncovered:
            raise ValueError(f"input maps leave {uncovered} of {self._sample_type.__name__} unfed")

        for m in self._output_maps:
            if m.output not in self._outputs:
                raise ValueError(f"{m} names unknown output {m.output!r}")
            if not hasattr(self._outputs[m.output].zeroMsgPayload, m.payload_field):
                raise ValueError(f"{m} names unknown payload field {m.payload_field!r}")

    def Reset(self, CurrentSimNanos: int) -> None:
        """Builds the algorithm at the reset time and writes its initial state.

        Raises:
            RuntimeError: naming any input whose reader is not subscribed.
            ValueError: naming any output map whose state field the built state lacks.
        """
        unlinked = sorted(name for name, reader in self._inputs.items() if not reader.isLinked())
        if unlinked:
            raise RuntimeError(f"inputs {unlinked} are not subscribed to any message")
        algorithm = self._make_algorithm(
            CurrentSimNanos / _NANOSECONDS_PER_SECOND, self._init_from()
        )
        missing = [m for m in self._output_maps if not hasattr(algorithm.state, m.state_field)]
        if missing:
            raise ValueError(f"the algorithm's state has no field for {missing}")
        self._algorithm = algorithm
        self._computed_ns = CurrentSimNanos
        self._write_outputs(algorithm.state, CurrentSimNanos)

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the algorithm to the current time when at least `PERIOD_S` has passed since the
        last compute.

        Raises:
            RuntimeError: before the first `Reset`, or naming any input never written.
        """
        algorithm = self.algorithm
        if CurrentSimNanos - self._computed_ns < _PERIOD_NS:
            return
        t = CurrentSimNanos / _NANOSECONDS_PER_SECOND

        unwritten = sorted(name for name, reader in self._inputs.items() if not reader.isWritten())
        if unwritten:
            raise RuntimeError(f"inputs {unwritten} have not been written at t = {t} s")
        payloads = {name: reader() for name, reader in self._inputs.items()}
        fields: dict[str, np.ndarray] = {}
        for m in self._input_maps:
            value = np.array(getattr(payloads[m.input], m.payload_field), dtype=float)
            fields[m.sample_field] = value if m.transform is None else m.transform(value)

        state = algorithm.step(self._sample_type(t=t, **fields))
        self._computed_ns = CurrentSimNanos
        self._write_outputs(state, CurrentSimNanos)

    def _write_outputs(self, state: HostedState, CurrentSimNanos: int) -> None:
        payloads: dict[str, Any] = {}
        for m in self._output_maps:
            if m.output not in payloads:
                payloads[m.output] = type(self._outputs[m.output].zeroMsgPayload)()
            value = getattr(state, m.state_field)
            setattr(
                payloads[m.output],
                m.payload_field,
                value.tolist() if isinstance(value, np.ndarray) else value,
            )
        for name, payload in payloads.items():
            self._outputs[name].write(payload, CurrentSimNanos, self.moduleID)
