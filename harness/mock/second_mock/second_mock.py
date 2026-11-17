"""The harness's second test mock, as an algorithm's notebook gives it: its class alone."""

from typing import Any

from fsw.codegen.fpp_types import named


class SecondMock:
    """Steps writing nothing."""

    def __init__(self, parameters: Any) -> None:
        """Takes its empty parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """

    def step(self, t: float) -> tuple[Any, None]:
        """Steps the mock.

        Args:
            t: s, the time.

        Returns:
            No output, and no telemetry.
        """
        return named("HarnessMock.SecondMockOutputs")(), None
