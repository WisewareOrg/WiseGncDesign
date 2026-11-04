"""A Basilisk Python `SysModel` hosting one algorithm, wired by its names."""

import inspect
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from Basilisk.architecture import messaging, sysModel

__all__ = ["STANDARD_MESSAGES", "AlgorithmModule"]

_NANOSECONDS_PER_SECOND = 1e9

STANDARD_MESSAGES: Mapping[str, tuple[type, tuple[str, ...]]] = MappingProxyType(
    {
        "nav_att": (messaging.NavAttMsg, ("sigma_BN", "omega_BN_B")),
        "nav_trans": (messaging.NavTransMsg, ("r_BN_N", "v_BN_N")),
    }
)
"""Basilisk's standard output messages, by the name the module gives each: its message type and
the standard fields it carries."""


class AlgorithmModule(sysModel.SysModel):
    """Hosts one algorithm inside a Basilisk task, wired by the names the algorithm uses.

    Each keyword of the algorithm's `step` other than `t` is a message field, read from the one
    input reader whose message has a field of that name. The algorithm's outputs are its public
    attributes other than `t`, each a standard field that one of `STANDARD_MESSAGES` carries.
    `Reset` writes the outputs as the algorithm holds them. Each `UpdateState` at a time after the
    algorithm's `t` reads every input once, calls `step(t=..., **fields)` with `t` in s, and writes
    the arrays it returns. The call Basilisk makes at the reset time itself leaves the state as
    built.

    Args:
        algorithm: the algorithm, built at the simulation's start time, holding `t` (s) and its
            outputs as attributes.
        inputs: reader by input role, each subscribed by the caller.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in: the flight
            software runs at 1 Hz.

    Raises:
        ValueError: at construction, naming a `step` keyword that no input's message carries or
            more than one does, or an output that no standard message carries.
    """

    period_s = 1.0

    def __init__(self, algorithm: Any, inputs: Mapping[str, Any]) -> None:
        """Resolves the algorithm's keywords against `inputs` and its outputs against messages.

        The outputs resolve against `STANDARD_MESSAGES`; the class docstring gives each argument.

        Raises:
            ValueError: as the class docstring states.
        """
        super().__init__()
        self._algorithm = algorithm
        self._inputs = MappingProxyType(dict(inputs))
        keywords = [k for k in inspect.signature(algorithm.step).parameters if k != "t"]
        self._reads = tuple((self._role(keyword), keyword) for keyword in keywords)
        self._names = tuple(n for n in vars(algorithm) if not n.startswith("_") and n != "t")
        carriers = {
            field: name for name, (_, fields) in STANDARD_MESSAGES.items() for field in fields
        }
        uncarried = sorted(n for n in self._names if n not in carriers)
        if uncarried:
            raise ValueError(f"no standard message carries the outputs {uncarried}")
        self._carriers = {n: carriers[n] for n in self._names}
        used = sorted(set(self._carriers.values()))
        self._outputs = MappingProxyType({name: STANDARD_MESSAGES[name][0]() for name in used})
        payloads = {name: type(m.zeroMsgPayload)() for name, m in self._outputs.items()}
        self._writes = tuple((payloads[carriers[n]], n) for n in self._names)
        self._sends = tuple((self._outputs[name].write, p) for name, p in payloads.items())
        self._readers = tuple(self._inputs.items())
        self._inputs_written = False

    def _role(self, keyword: str) -> str:
        """The input role whose message carries the field `keyword`.

        Args:
            keyword: one of the algorithm's `step` keywords, a message field name.

        Returns:
            The role in `inputs`.

        Raises:
            ValueError: when no input's message carries it, or more than one does.
        """
        roles = [r for r, reader in self._inputs.items() if hasattr(reader.zeroMsgPayload, keyword)]
        if len(roles) != 1:
            raise ValueError(f"step's {keyword!r} is carried by {len(roles)} inputs: {roles}")
        return roles[0]

    @property
    def inputs(self) -> Mapping[str, Any]:
        """Reader by input role."""
        return self._inputs

    @property
    def output_messages(self) -> Mapping[str, Any]:
        """Output message by name, the standard messages this module writes."""
        return self._outputs

    @property
    def outputs(self) -> Mapping[str, Any]:
        """Output message by output name: the standard message each output is written to."""
        return MappingProxyType({name: self._outputs[self._carriers[name]] for name in self._names})

    @property
    def algorithm(self) -> Any:
        """The hosted algorithm, for inspection."""
        return self._algorithm

    def Reset(self, CurrentSimNanos: int) -> None:
        """Writes the algorithm's outputs as it holds them.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            RuntimeError: naming any input whose reader is not subscribed.
        """
        unlinked = sorted(name for name, reader in self._readers if not reader.isLinked())
        if unlinked:
            raise RuntimeError(f"inputs {unlinked} are not subscribed to any message")
        self._write_outputs(
            {name: getattr(self._algorithm, name) for name in self._names}, CurrentSimNanos
        )

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Steps the algorithm to the current time when it lies after the algorithm's `t`.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            RuntimeError: naming any input never written.
        """
        t = CurrentSimNanos / _NANOSECONDS_PER_SECOND
        if not t > self._algorithm.t:
            return

        if not self._inputs_written:
            unwritten = sorted(name for name, reader in self._readers if not reader.isWritten())
            if unwritten:
                raise RuntimeError(f"inputs {unwritten} have not been written at t = {t} s")
            self._inputs_written = True
        payloads = {name: reader() for name, reader in self._readers}
        fields = {
            keyword: np.array(getattr(payloads[role], keyword), dtype=float)
            for role, keyword in self._reads
        }
        self._write_outputs(self._algorithm.step(t=t, **fields), CurrentSimNanos)

    def _write_outputs(self, values: Mapping[str, Any], CurrentSimNanos: int) -> None:
        """Copies each output's array into its message field and writes every output message.

        Args:
            values: output name to its array.
            CurrentSimNanos: ns, the time the messages are written at.
        """
        for payload, name in self._writes:
            value = values[name]
            setattr(payload, name, value.tolist() if isinstance(value, np.ndarray) else value)
        module_id = self.moduleID
        for write, payload in self._sends:
            write(payload, CurrentSimNanos, module_id)
