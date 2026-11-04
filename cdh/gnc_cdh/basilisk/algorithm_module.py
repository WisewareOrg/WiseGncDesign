"""A Basilisk Python `SysModel` hosting one framework-free algorithm, by its `Binding`."""

import dataclasses
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from gnc_cdh.basilisk.bindings import Binding

__all__ = ["AlgorithmModule"]

_NANOSECONDS_PER_SECOND = 1e9


class AlgorithmModule(sysModel.SysModel):
    """Hosts one algorithm inside a Basilisk task, copying message fields into its sample and its
    state into messages by the names its `Binding` gives, and nothing more.

    `Reset` builds the algorithm as `binding.algorithm(t0=..., **init_from())`, `t0` being the
    reset time in s, and writes its initial state to every output. Each `UpdateState` at a time
    after the algorithm's state time reads every input once, builds one `binding.sample` with `t`
    in s, calls `algorithm.step(sample)`, and writes the returned state. The call Basilisk makes
    at the reset time itself leaves the state as built.

    Args:
        binding: what the algorithm reads and writes.
        inputs: reader by input role, each subscribed by the caller.
        init_from: returns the algorithm's constructor arguments other than `t0`, called at each
            `Reset`.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in: the flight
            software runs at 1 Hz.

    Raises:
        ValueError: at construction, naming the sample field, role, message or message field the
            binding gets wrong.
    """

    period_s = 1.0

    def __init__(
        self,
        binding: Binding,
        inputs: Mapping[str, Any],
        init_from: Callable[[], Mapping[str, Any]],
    ) -> None:
        super().__init__()
        self._binding = binding
        self._inputs = MappingProxyType(dict(inputs))
        self._outputs = MappingProxyType({name: kind() for name, kind in binding.messages.items()})
        self._init_from = init_from
        self._algorithm: Any = None
        self._validate()
        self._readers = tuple(self._inputs.items())
        self._reads = tuple(
            (role, message_field, sample_field)
            for sample_field, (role, message_field) in binding.inputs.items()
        )
        payloads = {name: type(m.zeroMsgPayload)() for name, m in self._outputs.items()}
        self._writes = tuple(
            (payloads[message], state_field, message_field)
            for state_field, (message, message_field) in binding.outputs.items()
        )
        self._sends = tuple((self._outputs[name].write, p) for name, p in payloads.items())
        self._inputs_written = False

    @property
    def inputs(self) -> Mapping[str, Any]:
        """Reader by input role."""
        return self._inputs

    @property
    def output_messages(self) -> Mapping[str, Any]:
        """Output message by name, the messages this module writes."""
        return self._outputs

    @property
    def algorithm(self) -> Any:
        """The hosted instance, built by the latest `Reset`, for inspection.

        Raises:
            RuntimeError: before the first `Reset`.
        """
        if self._algorithm is None:
            raise RuntimeError("AlgorithmModule has not been Reset")
        return self._algorithm

    def _validate(self) -> None:
        sample = self._binding.sample
        if not dataclasses.is_dataclass(sample) or "t" not in {
            f.name for f in dataclasses.fields(sample)
        }:
            raise ValueError(f"sample {sample!r} is not a dataclass with field 't'")
        fields = {f.name for f in dataclasses.fields(sample)} - {"t"}
        named = sorted(self._binding.inputs)
        if set(named) != fields:
            raise ValueError(f"inputs name {named}; {sample.__name__} has {sorted(fields)}")
        for sample_field, (role, message_field) in self._binding.inputs.items():
            if role not in self._inputs:
                raise ValueError(f"{sample_field!r} reads role {role!r}, absent from inputs")
            if not hasattr(self._inputs[role].zeroMsgPayload, message_field):
                raise ValueError(f"role {role!r}'s message has no field {message_field!r}")
        for state_field, (message, message_field) in self._binding.outputs.items():
            if message not in self._outputs:
                raise ValueError(
                    f"{state_field!r} writes message {message!r}, absent from messages"
                )
            if not hasattr(self._outputs[message].zeroMsgPayload, message_field):
                raise ValueError(f"message {message!r} has no field {message_field!r}")

    def Reset(self, CurrentSimNanos: int) -> None:
        """Builds the algorithm at the reset time and writes its initial state.

        Raises:
            RuntimeError: naming any input whose reader is not subscribed.
            ValueError: naming any output state field the built state lacks.
        """
        unlinked = sorted(name for name, reader in self._readers if not reader.isLinked())
        if unlinked:
            raise RuntimeError(f"inputs {unlinked} are not subscribed to any message")
        algorithm = self._binding.algorithm(
            t0=CurrentSimNanos / _NANOSECONDS_PER_SECOND, **self._init_from()
        )
        missing = sorted(f for f in self._binding.outputs if not hasattr(algorithm.state, f))
        if missing:
            raise ValueError(f"the algorithm's state has no field {missing}")
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
        fields = {
            sample_field: np.array(getattr(payloads[role], message_field), dtype=float)
            for role, message_field, sample_field in self._reads
        }
        state = algorithm.step(self._binding.sample(t=t, **fields))
        self._write_outputs(state, CurrentSimNanos)

    def _write_outputs(self, state: Any, CurrentSimNanos: int) -> None:
        for payload, state_field, message_field in self._writes:
            value = getattr(state, state_field)
            setattr(
                payload, message_field, value.tolist() if isinstance(value, np.ndarray) else value
            )
        module_id = self.moduleID
        for write, payload in self._sends:
            write(payload, CurrentSimNanos, module_id)
