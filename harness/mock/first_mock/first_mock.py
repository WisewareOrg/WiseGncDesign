"""The harness's first test mock, as an algorithm's notebook gives it: its class and parameters."""

from typing import Any

from fsw.codegen.fpp_types import named


class FirstMock:
    """Steps writing nothing until commanded to fail; its next step then raises."""

    def __init__(self, parameters: Any) -> None:
        """Starts not failing.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        self._failing = False

    def fail(self) -> None:
        """Makes the next step raise."""
        self._failing = True

    def step(self, t: float) -> tuple[Any, None]:
        """Steps the mock.

        Args:
            t: s, the time.

        Returns:
            No output, and no telemetry.

        Raises:
            ZeroDivisionError: the mock was commanded to fail.
        """
        if self._failing:
            raise ZeroDivisionError("the tick's own bug")
        return named("HarnessMock.FirstMockOutputs")(), None


def parameters(scenario: Any) -> Any:
    """The mock's parameters for one case: its gain is the scenario's Earth `mu`.

    Args:
        scenario: the case's dispersed scenario.

    Returns:
        The parameters, which the ground writes as the case's record.
    """
    return named("HarnessMock.FirstMockParameters")(gain=scenario.mu_m3_s2["earth"])
