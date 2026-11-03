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

__all__ = ["AlgorithmModule", "InputMap", "OutputMap"]

_NANOSECONDS_PER_SECOND = 1e9


class AlgorithmModule(sysModel.SysModel):
    """Hosts one algorithm inside a Basilisk task.

    `Reset` builds the algorithm as `make_algorithm(t0, init_from())`, `t0` being the reset
    time in s, and writes its initial state to every output. Each `UpdateState` at a time
    after the algorithm's state time reads every input once, builds one `sample_type` instance
    from the input maps with `t` in s, calls `algorithm.step(sample)`, and writes the returned
    state through the output maps. The call Basilisk makes at the reset time itself leaves the
    state as built.

    Args:
        inputs: reader by input name, each subscribed by the caller.
        outputs: output message by name.
        input_maps: cover every field of `sample_type` other than `t`, each exactly once.
        output_maps: name only known outputs and their payload fields.
        sample_type: a dataclass with field `t` (s).
        make_algorithm: builds the algorithm from `t0` (s) and the initial-state mapping.
        init_from: returns the initial-state mapping, called at each `Reset`.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in: the flight
            software runs at 1 Hz.

    Raises:
        ValueError: at construction, naming the earliest map that refers to an unknown input,
            output or payload field, or a sample field that is unknown, duplicated or left
            uncovered.
    """

    period_s = 1.0

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
        self._validate_maps()
        self._readers = tuple(self._inputs.items())
        self._reads = tuple(
            (m.input, m.payload_field, m.sample_field, m.transform) for m in self._input_maps
        )
        payloads: dict[str, Any] = {}
        for m in self._output_maps:
            payloads.setdefault(m.output, type(self._outputs[m.output].zeroMsgPayload)())
        self._writes = tuple(
            (payloads[m.output], m.state_field, m.payload_field) for m in self._output_maps
        )
        self._sends = tuple((self._outputs[name].write, p) for name, p in payloads.items())
        self._inputs_written = False

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
        self._write_outputs(algorithm.state, CurrentSimNanos)

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the algorithm to the current time when it lies after the state's time.

        Raises:
            RuntimeError: before the first `Reset`, or naming any input never written.
        """
        algorithm = self.algorithm
        t = CurrentSimNanos / _NANOSECONDS_PER_SECOND
        if not t > algorithm.state.t:
            return

        if not self._inputs_written:
            unwritten = sorted(name for name, reader in self._readers if not reader.isWritten())
            if unwritten:
                raise RuntimeError(f"inputs {unwritten} have not been written at t = {t} s")
            self._inputs_written = True
        payloads = {name: reader() for name, reader in self._readers}
        fields: dict[str, np.ndarray] = {}
        for input_name, payload_field, sample_field, transform in self._reads:
            value = np.array(getattr(payloads[input_name], payload_field), dtype=float)
            fields[sample_field] = value if transform is None else transform(value)

        state = algorithm.step(self._sample_type(t=t, **fields))
        self._write_outputs(state, CurrentSimNanos)

    def _write_outputs(self, state: HostedState, CurrentSimNanos: int) -> None:
        for payload, state_field, payload_field in self._writes:
            value = getattr(state, state_field)
            setattr(
                payload, payload_field, value.tolist() if isinstance(value, np.ndarray) else value
            )
        module_id = self.moduleID
        for write, payload in self._sends:
            write(payload, CurrentSimNanos, module_id)
