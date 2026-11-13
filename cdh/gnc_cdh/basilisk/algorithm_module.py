"""A Basilisk Python `SysModel` hosting one algorithm, wired by its names."""

import inspect
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from gnc_cdh import UNITS

__all__ = ["AlgorithmModule"]

_NANOSECONDS_PER_SECOND = 1e9


class AlgorithmModule(sysModel.SysModel):
    """Hosts one algorithm inside a Basilisk task, wired by the names the algorithm uses.

    Each keyword of the algorithm's `step` other than `t` is a message field, read from the one
    input reader whose message has a field of that name. The algorithm's outputs are its public
    attributes other than `t`, each an estimate named in `gnc_cdh.UNITS`. `Reset` logs the outputs
    as the algorithm holds them. Each `UpdateState` at a time after the algorithm's `t` reads every
    input once, calls `step(t=..., **fields)` with `t` in s, and logs the arrays it returns, by the
    tick's time in ns. `fly` records the log as the estimate. The call Basilisk makes at the reset
    time itself leaves the state as built.

    Attributes:
        period_s: the period, in s, of the task the simulation runs this module in: the flight
            software runs at 1 Hz.
    """

    period_s = 1.0

    def __init__(self, algorithm: Any, inputs: Mapping[str, Any]) -> None:
        """Resolves the algorithm's keywords against `inputs` and checks its outputs.

        Args:
            algorithm: the algorithm, built at the simulation's start time, holding `t` (s) and
                its outputs as attributes.
            inputs: reader by input role, each subscribed by the caller.

        Raises:
            ValueError: naming a `step` keyword that no input's message carries or more than one
                does, or an output that `gnc_cdh.UNITS` does not name.
        """
        super().__init__()
        self._algorithm = algorithm
        self._inputs = MappingProxyType(dict(inputs))
        keywords = [k for k in inspect.signature(algorithm.step).parameters if k != "t"]
        self._reads = tuple((self._role(keyword), keyword) for keyword in keywords)
        self._names = tuple(n for n in vars(algorithm) if not n.startswith("_") and n != "t")
        unnamed = sorted(n for n in self._names if n not in UNITS)
        if unnamed:
            raise ValueError(f"outputs {unnamed} are not estimates gnc_cdh.UNITS names")
        self._readers = tuple(self._inputs.items())
        self._inputs_written = False
        self._log: dict[int, dict[str, np.ndarray]] = {}

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
    def build(self) -> dict[str, str]:
        """The host's build identity, recorded in a flight's `flight.json`."""
        return {"host": "gnc_cdh.basilisk.AlgorithmModule"}

    @property
    def inputs(self) -> Mapping[str, Any]:
        """Reader by input role."""
        return self._inputs

    @property
    def algorithm(self) -> Any:
        """The hosted algorithm, for inspection."""
        return self._algorithm

    def Reset(self, CurrentSimNanos: int) -> None:
        """Logs the algorithm's outputs as it holds them.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            RuntimeError: naming any input whose reader is not subscribed.
        """
        unlinked = sorted(name for name, reader in self._readers if not reader.isLinked())
        if unlinked:
            raise RuntimeError(f"inputs {unlinked} are not subscribed to any message")
        self._log = {CurrentSimNanos: self._logged(vars(self._algorithm))}

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
        self._log[CurrentSimNanos] = self._logged(self._algorithm.step(t=t, **fields))

    def fly(self, run: Callable[[Any, dict[str, tuple[Any, str, str]]], dict]) -> dict:
        """Flies the scenario through `run` and records the estimate from the log.

        Args:
            run: flies the scenario with this host and the datasets to record, as the harness
                binds it from the scenario and its stopping rule.

        Returns:
            The run's datasets with the estimate's added.
        """
        datasets = run(self, {})
        datasets.update(self.estimate_datasets(datasets["t_s"][0]))
        return datasets

    def estimate_datasets(self, t_s: np.ndarray) -> dict[str, tuple[np.ndarray, str]]:
        """The estimate's run-file datasets at the record times, from the log.

        Args:
            t_s: (N,) s, the record times, each one a tick's time to the nanosecond.

        Returns:
            `est/<output>` for each output, its rows at `t_s`, with its units.

        Raises:
            KeyError: naming a record time no tick logged.
        """
        rows = []
        for t in t_s:
            t_ns = round(float(t) * _NANOSECONDS_PER_SECOND)
            if t_ns not in self._log:
                raise KeyError(f"no estimate was logged at t = {t} s")
            rows.append(self._log[t_ns])
        return {
            f"est/{name}": (np.array([row[name] for row in rows]), UNITS[name])
            for name in self._names
        }

    def _logged(self, values: Mapping[str, Any]) -> dict[str, np.ndarray]:
        """A copy of each output's array, as the log keeps it.

        Args:
            values: output name to its array, and possibly other names.

        Returns:
            Output name to a copy of its array.
        """
        return {name: np.array(values[name], dtype=float) for name in self._names}
