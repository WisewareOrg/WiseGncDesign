"""The Python build's CDH dispatches each command by name to its instance's method of that name."""

from collections import namedtuple
from pathlib import Path

import numpy as np
import pytest

from fsw.python.cdh import commands
from ground.dictionary import Dictionary

TOY = """\
module Toy {

  passive component Toy {
    sync command setGain(gain: F64)
    sync command reset
    telemetry gain: F64
    param offset: F64
    time get port timeCaller
    telemetry port tlmOut
    command reg port cmdRegOut
    command recv port cmdIn
    command resp port cmdResponseOut
    param get port prmGetOut
    param set port prmSetOut
  }

}
"""

ToyTelemetry = namedtuple("ToyTelemetry", ["gain"], defaults=[None])
"""The toy's telemetry tuple."""


class Toy:
    """A toy algorithm: `setGain` refuses a negative gain, `reset` writes nothing."""

    def setGain(self, gain: float) -> ToyTelemetry:
        """Takes the gain, refusing a negative one.

        Args:
            gain: the gain.

        Returns:
            `gain`.

        Raises:
            ValueError: the gain is negative.
        """
        if gain < 0.0:
            raise ValueError(f"gain {gain} is negative")
        return ToyTelemetry(gain=gain)

    def reset(self) -> None:
        """Writes nothing."""


@pytest.fixture(scope="module")
def dictionary(tmp_path_factory: pytest.TempPathFactory) -> Dictionary:
    """The toy's dictionary, instanced as `toy`.

    Args:
        tmp_path_factory: where the toy's model is written.

    Returns:
        The dictionary.
    """
    model = tmp_path_factory.mktemp("toy") / "Toy.fpp"
    model.write_text(TOY)
    return Dictionary.from_component([Path(model)], "Toy.Toy", instance="toy")


def test_each_command_answers_with_its_f_prime_response(dictionary: Dictionary):
    """Each `Fw.CmdResponse` a command can get, by name, with the handler's telemetry.

    A handler that returns answers `OK` with its telemetry's writes; one refusing answers
    `VALIDATION_ERROR` with its reason; a name not the instance's, or a parameter's set or save
    command, answers `INVALID_OPCODE`.

    Args:
        dictionary: the toy's dictionary.
    """
    handlers = commands.handlers(dictionary, {"toy": Toy()})

    assert commands.dispatch(handlers, "toy.setGain", {"gain": 2.0}) == (
        "OK",
        None,
        [("toy.gain", 2.0)],
    )
    assert commands.dispatch(handlers, "toy.reset", {}) == ("OK", None, [])
    assert commands.dispatch(handlers, "toy.setGain", {"gain": -1.0}) == (
        "VALIDATION_ERROR",
        "gain -1.0 is negative",
        [],
    )
    for name in ("toy.setGian", "toy.OFFSET_PRM_SET", "toy.OFFSET_PRM_SAVE", "other.reset"):
        assert commands.dispatch(handlers, name, {}) == ("INVALID_OPCODE", None, [])


def test_a_handler_s_other_exception_is_a_bug_and_propagates(dictionary: Dictionary):
    """Anything but `ValueError` from a handler is raised whole.

    Args:
        dictionary: the toy's dictionary.
    """

    class Broken(Toy):
        """A toy whose `reset` fails."""

        def reset(self) -> None:
            """Fails.

            Raises:
                ZeroDivisionError: always.
            """
            raise ZeroDivisionError("broken")

    handlers = commands.handlers(dictionary, {"toy": Broken()})

    with pytest.raises(ZeroDivisionError, match="broken"):
        commands.dispatch(handlers, "toy.reset", {})


@pytest.mark.parametrize(
    "algorithm",
    [
        object(),
        type("Renamed", (Toy,), {"setGain": lambda self, value: None})(),
        type("Extra", (Toy,), {"setGain": lambda self, gain, scale: None})(),
    ],
    ids=["no method", "other parameter", "extra parameter"],
)
def test_a_command_the_algorithm_lacks_or_declares_otherwise_is_refused_naming_it(
    dictionary: Dictionary, algorithm: object
):
    """Every command of the instance must be a method taking FPP's parameters, by name.

    Args:
        dictionary: the toy's dictionary.
        algorithm: an algorithm lacking `setGain`, or declaring it with another parameter.
    """
    with pytest.raises(ValueError, match=r"toy\.setGain takes \['gain'\]"):
        commands.handlers(dictionary, {"toy": algorithm})


def test_arguments_reach_the_handler_as_given(dictionary: Dictionary):
    """The handler gets each argument by its parameter's name, unconverted.

    Args:
        dictionary: the toy's dictionary.
    """
    received = []

    class Recording(Toy):
        """A toy keeping what `setGain` receives."""

        def setGain(self, gain: float) -> None:
            """Keeps the gain.

            Args:
                gain: the gain.
            """
            received.append(gain)

    gain = np.float64(0.5)
    commands.dispatch(
        commands.handlers(dictionary, {"toy": Recording()}), "toy.setGain", {"gain": gain}
    )

    assert received == [gain]
    assert received[0] is gain
