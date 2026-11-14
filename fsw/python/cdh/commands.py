"""The Python build's command dispatch: each command, by name, to its instance's method.

Every command the dictionary gives a GNC instance is a method of its algorithm, named and
parametered as in FPP, but for the set and save commands F´ generates for each parameter, which are
not the algorithm's. A handler that returns answers `OK`, and one that raises `ValueError` answers
`VALIDATION_ERROR` with the error's message as the reason; a name that is not a handler's answers
`INVALID_OPCODE`; any other exception is a bug and propagates. A handler returns its algorithm's
`<Name>Telemetry` tuple, or `None`.
"""

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from fsw.python.cdh import telemetry
from ground.dictionary import Dictionary

__all__ = ["dispatch", "handlers"]

Handlers = dict[str, tuple[str, Callable[..., Any]]]
"""Each command's handler, by `<instance>.<command>`, with its instance's name."""


def handlers(dictionary: Dictionary, algorithms: Mapping[str, Any]) -> Handlers:
    """Each command of each instance, resolved to its algorithm's method.

    Args:
        dictionary: the dictionary holding the instances.
        algorithms: each algorithm, by its instance's name, such as `nav`.

    Returns:
        The handlers.

    Raises:
        ValueError: naming a command the algorithm lacks or declares with other parameters.
    """
    resolved: Handlers = {}
    for instance, algorithm in algorithms.items():
        for name, params in dictionary.entries(instance)["commands"].items():
            if dictionary.command(f"{instance}.{name}").kind in ("set", "save"):
                continue
            handler = getattr(algorithm, name, None)
            found = list(inspect.signature(handler).parameters) if callable(handler) else None
            wanted = [param for param, _ in params]
            if found != wanted:
                raise ValueError(
                    f"{instance}.{name} takes {wanted}; the algorithm has "
                    f"{'no such method' if found is None else found}"
                )
            resolved[f"{instance}.{name}"] = instance, handler
    return resolved


def dispatch(
    handlers: Handlers, name: str, args: Mapping[str, Any]
) -> tuple[str, str | None, list[tuple[str, Any]]]:
    """Runs a command's handler.

    Args:
        handlers: the handlers, as `handlers` gives them.
        name: `<instance>.<command>`.
        args: the arguments by parameter name, as `Dictionary.arguments` types them.

    Returns:
        The `Fw.CmdResponse` name, the message of the `ValueError` the handler refused the command
        with, else `None`, and the telemetry the handler wrote, as `telemetry.writes` gives it.
    """
    if name not in handlers:
        return "INVALID_OPCODE", None, []
    instance, handler = handlers[name]
    try:
        written = handler(**args)
    except ValueError as error:
        return "VALIDATION_ERROR", str(error), []
    return "OK", None, telemetry.writes(instance, written)
