"""The Python build's command dispatch: each command, by name, to its instance's method.

Every command the dictionary gives a GNC instance is a method of its algorithm, named and
parametered as in FPP, but for the set and save commands F´ generates for each parameter, which are
not the algorithm's. A handler that returns answers `OK`, and one that raises `Refused` answers
`VALIDATION_ERROR` with the exception's message as the reason, as F´'s handler refuses on its
response port; a name that is not a handler's answers `INVALID_OPCODE`; any other exception,
`ValueError` included, is a bug and propagates. A handler returns its algorithm's
`<Name>Telemetry` tuple, or `None`.
"""

import inspect
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

from fsw.codegen.dictionary import Dictionary
from fsw.python.cdh import telemetry

__all__ = ["Dispatched", "Handler", "Handlers", "Refused", "dispatch", "handlers"]


class Refused(Exception):
    """Raised by a handler to refuse its command; its message is the reason the ground gets."""


class Handler(NamedTuple):
    """A command's handler.

    Attributes:
        instance: its algorithm's instance's unqualified name in the sub-topology.
        method: the algorithm's method of the command's name.
    """

    instance: str
    method: Callable[..., Any]


class Dispatched(NamedTuple):
    """What running a command gave.

    Attributes:
        response: the `Fw.CmdResponse` name.
        reason: the message of the `Refused` the handler refused the command with, else `None`.
        writes: the telemetry the handler wrote, as `telemetry.writes` gives it.
    """

    response: str
    reason: str | None
    writes: list[tuple[str, int, Any]]


Handlers = dict[str, Handler]
"""Each command's handler, by `<instance>.<command>`."""


def handlers(dictionary: Dictionary, algorithms: Mapping[str, Any]) -> Handlers:
    """Each command of each instance, resolved to its algorithm's method.

    Args:
        dictionary: the dictionary holding the instances.
        algorithms: each algorithm, by its instance's unqualified name.

    Returns:
        The handlers.

    Raises:
        ValueError: naming a command the algorithm lacks or declares with other parameters.
    """
    resolved: Handlers = {}
    for instance, algorithm in algorithms.items():
        for command in dictionary.commands(instance):
            if command.kind in ("set", "save"):
                continue
            name = command.name.removeprefix(f"{instance}.")
            handler = getattr(algorithm, name, None)
            found = list(inspect.signature(handler).parameters) if callable(handler) else None
            wanted = list(command.params)
            if not callable(handler) or found != wanted:
                raise ValueError(
                    f"{instance}.{name} takes {wanted}; the algorithm has "
                    f"{'no such method' if found is None else found}"
                )
            resolved[f"{instance}.{name}"] = Handler(instance, handler)
    return resolved


def dispatch(table: Handlers, name: str, args: Mapping[str, Any], t_ns: int) -> Dispatched:
    """Runs a command's handler.

    Args:
        table: the handlers, as `handlers` gives them.
        name: `<instance>.<command>`.
        args: the arguments by parameter name, as `Dictionary.arguments` types them.
        t_ns: ns, the tick's time, which tags the handler's writes.

    Returns:
        Its response, its reason and its writes.
    """
    if name not in table:
        return Dispatched("INVALID_OPCODE", None, [])
    handler = table[name]
    try:
        written = handler.method(**args)
    except Refused as error:
        return Dispatched("VALIDATION_ERROR", str(error), [])
    return Dispatched("OK", None, telemetry.writes(handler.instance, written, t_ns))
