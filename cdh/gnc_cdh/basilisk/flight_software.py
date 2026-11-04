"""Builds a named algorithm's Basilisk host module from its `Binding` and the caller's readers."""

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from gnc_cdh.basilisk.algorithm_module import AlgorithmModule
from gnc_cdh.basilisk.bindings import BINDINGS

__all__ = ["make_fsw"]

_TIME_PARAMETER = "t0"


def make_fsw(
    name: str,
    inputs: Mapping[str, Any],
    initial_state: Callable[[], Mapping[str, Any]],
    **params: Any,
) -> AlgorithmModule:
    """Builds the `AlgorithmModule` hosting the algorithm bound as `name`.

    Args:
        name: a key of `BINDINGS`.
        inputs: reader by input role, each subscribed by the caller; roles the binding reads
            nothing from are left out of the module.
        initial_state: returns initial-state values by constructor parameter name, called at
            each `Reset`; keys naming no parameter are left out.
        **params: further constructor parameters, such as `mu` (m^3/s^2) and the IMU mounting
            `dcm_PB`.

    Raises:
        ValueError: when `name` is unknown, a role the binding reads is absent from `inputs`, or
            a key of `params` names no constructor parameter. At `Reset`, when `initial_state()`
            and `params` share a key or together miss a required parameter.
    """
    try:
        binding = BINDINGS[name]
    except KeyError:
        raise ValueError(f"no algorithm {name!r}; known: {sorted(BINDINGS)}") from None
    parameters = {
        n: p
        for n, p in inspect.signature(binding.algorithm).parameters.items()
        if n != _TIME_PARAMETER
    }
    unknown = sorted(set(params) - set(parameters))
    if unknown:
        raise ValueError(f"params {unknown} name no parameter of {name!r}")
    roles = {role for role, _ in binding.inputs.values()}
    absent = sorted(roles - set(inputs))
    if absent:
        raise ValueError(f"inputs has no role {absent}; {name!r} reads them")
    required = [n for n, p in parameters.items() if p.default is inspect.Parameter.empty]

    def init_from() -> dict[str, Any]:
        """The constructor arguments other than `t0`.

        They are `initial_state()` and `params` merged, cut to the constructor's parameters.

        Raises:
            ValueError: when they share a key or together miss a required parameter.
        """
        state = dict(initial_state())
        shared = sorted(set(state) & set(params))
        if shared:
            raise ValueError(f"initial_state() and params both supply {shared}")
        merged = {**state, **params}
        missing = [n for n in required if n not in merged]
        if missing:
            raise ValueError(f"{binding.algorithm.__name__} needs {missing}")
        return {n: merged[n] for n in parameters if n in merged}

    return AlgorithmModule(binding, {role: inputs[role] for role in roles}, init_from)
