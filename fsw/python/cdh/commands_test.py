"""The Python build's CDH dispatches each command by name to its instance's method of that name."""

from typing import Any

import numpy as np
import pytest

from fsw.codegen import fpp_types
from fsw.codegen.dictionary import Dictionary
from fsw.codegen.fpp_types import named
from fsw.mock import MOCK
from fsw.python.cdh import commands


class Source:
    """`fsw.mock`'s `MockGnc.Source`: `setLevel` refuses a negative level; `reset` writes none."""

    def setLevel(self, level: float) -> Any:
        """Takes the level, refusing a negative one.

        Args:
            level: the level.

        Returns:
            `level`, written.

        Raises:
            ValueError: the level is negative.
        """
        if level < 0.0:
            raise ValueError(f"level {level} is negative")
        return named("MockGnc.SourceTelemetry")(level=level)

    def reset(self) -> None:
        """Writes nothing."""


@pytest.fixture(scope="module")
def dictionary() -> Dictionary:
    """The dictionary of `MockFrame` of `fsw.mock.MOCK`, whose `source` is mocked.

    It loads `MOCK`'s tuples, which `Source.setLevel`'s `named` resolves.

    Returns:
        The dictionary.
    """
    fpp_types.load(MOCK)
    return Dictionary.from_sub_topology("MockFrame", contract=MOCK)


def test_each_command_answers_with_its_f_prime_response(dictionary: Dictionary):
    """Each `Fw.CmdResponse` a command can get, by name, with the handler's telemetry.

    A handler that returns answers `OK` with its telemetry's writes; one refusing answers
    `VALIDATION_ERROR` with its reason; a name not the instance's, or a parameter's set or save
    command, answers `INVALID_OPCODE`.

    Args:
        dictionary: the mock's dictionary.
    """
    handlers = commands.handlers(dictionary, {"source": Source()})

    assert commands.dispatch(handlers, "source.setLevel", {"level": 2.0}) == (
        "OK",
        None,
        [("source.level", 2.0)],
    )
    assert commands.dispatch(handlers, "source.reset", {}) == ("OK", None, [])
    assert type(commands.dispatch(handlers, "source.reset", {})) is commands.Dispatched
    assert commands.dispatch(handlers, "source.setLevel", {"level": -1.0}) == (
        "VALIDATION_ERROR",
        "level -1.0 is negative",
        [],
    )
    for name in ("source.setLevle", "source.GAIN_PRM_SET", "source.GAIN_PRM_SAVE", "other.reset"):
        assert commands.dispatch(handlers, name, {}) == ("INVALID_OPCODE", None, [])


def test_a_handler_s_other_exception_is_a_bug_and_propagates(dictionary: Dictionary):
    """Anything but `ValueError` from a handler is raised whole.

    Args:
        dictionary: the mock's dictionary.
    """

    class Broken(Source):
        """A mock whose `reset` fails."""

        def reset(self) -> None:
            """Fails.

            Raises:
                ZeroDivisionError: always.
            """
            raise ZeroDivisionError("broken")

    handlers = commands.handlers(dictionary, {"source": Broken()})

    with pytest.raises(ZeroDivisionError, match="broken"):
        commands.dispatch(handlers, "source.reset", {})


@pytest.mark.parametrize(
    "algorithm",
    [
        object(),
        type("Renamed", (Source,), {"setLevel": lambda self, value: None})(),
        type("Extra", (Source,), {"setLevel": lambda self, level, scale: None})(),
    ],
    ids=["no method", "other parameter", "extra parameter"],
)
def test_a_command_the_algorithm_lacks_or_declares_otherwise_is_refused_naming_it(
    dictionary: Dictionary, algorithm: object
):
    """Every command of the instance must be a method taking FPP's parameters, by name.

    Args:
        dictionary: the mock's dictionary.
        algorithm: an algorithm lacking `setLevel`, or declaring it with another parameter.
    """
    with pytest.raises(ValueError, match=r"source\.setLevel takes \['level'\]"):
        commands.handlers(dictionary, {"source": algorithm})


def test_arguments_reach_the_handler_as_given(dictionary: Dictionary):
    """The handler gets each argument by its parameter's name, unconverted.

    Args:
        dictionary: the mock's dictionary.
    """
    received = []

    class Recording(Source):
        """A mock keeping what `setLevel` receives."""

        def setLevel(self, level: float) -> None:
            """Keeps the level.

            Args:
                level: the level.
            """
            received.append(level)

    level = np.float64(0.5)
    commands.dispatch(
        commands.handlers(dictionary, {"source": Recording()}), "source.setLevel", {"level": level}
    )

    assert received == [level]
    assert received[0] is level
