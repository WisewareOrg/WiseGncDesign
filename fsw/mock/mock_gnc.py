"""The test mock algorithms `MockGnc.Source` and `MockGnc.Sink`, as a notebook gives an algorithm.

Their Python twins log what they are given, in `LOG`, and write what the tests need. The component
tuples they build resolve once `fsw.codegen.fpp_types.load(MOCK)` has run.
"""

from typing import Any

from fsw.codegen.fpp_types import named
from fsw.python.cdh.commands import Refused

__all__ = ["LOG", "Sink", "Source"]

LOG: list[tuple] = []
"""Each call a mock algorithm received, in order: its instance, what it was, what it was given."""


class Source:
    """The mock that runs first: each step it sends its level times its gain, plus the time."""

    def __init__(self, parameters: Any) -> None:
        """Logs its parameters, and starts at level 0.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        LOG.append(("source", "boot", parameters))
        self._gain = parameters.gain
        self._level = 0.0

    def setLevel(self, level: float) -> Any:
        """Sets the level each later sample carries, refusing a negative one.

        Args:
            level: the level.

        Returns:
            The level, written.

        Raises:
            Refused: the level is negative.
        """
        if level < 0.0:
            raise Refused(f"level {level} is negative")
        LOG.append(("source", "setLevel", level))
        self._level = level
        return named("MockGnc.SourceTelemetry")(level=level)

    def reset(self) -> None:
        """Writes nothing."""

    def step(self, t: float) -> tuple[Any, Any]:
        """Logs the step and sends the sample.

        Args:
            t: s, the time.

        Returns:
            The sample, and the level, written.
        """
        LOG.append(("source", "step", t))
        sample = named("MockGnc.Sample")(value=self._gain * self._level + t)
        return named("MockGnc.SourceOutputs")(sampleOut=sample), named("MockGnc.SourceTelemetry")(level=self._level)


class Sink:
    """The mock that runs second: it writes the sample it receives, offset."""

    def __init__(self, parameters: Any) -> None:
        """Logs its parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        LOG.append(("sink", "boot", parameters))
        self._offset = parameters.offset

    def step(self, t: float, sample: Any) -> tuple[Any, Any]:
        """Logs the step and the sample it holds, and writes it offset.

        Args:
            t: s, the time.
            sample: the source's latest sample.

        Returns:
            No output, and the sample received, offset.
        """
        LOG.append(("sink", "step", t, sample))
        written = named("MockGnc.SinkTelemetry")(received=sample.value + self._offset)
        return named("MockGnc.SinkOutputs")(), written
