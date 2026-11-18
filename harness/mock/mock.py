"""The harness's test mock, as an algorithm's notebook gives it: its class and its parameters."""

from typing import Any

import numpy as np

from fsw.codegen.fpp_types import named


class Mock:
    """Writes the nav role's estimate channels with a fixed state at every step.

    Once commanded to fail, its next step raises.
    """

    def __init__(self, parameters: Any) -> None:
        """Starts not failing.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        self._failing = False

    def fail(self) -> None:
        """Makes the next step raise."""
        self._failing = True

    def initNavState(self, epoch: float, attitude: Any, position: Any, velocity: Any) -> None:
        """Takes the commanded state and does nothing with it.

        Args:
            epoch: s, the FSW time the state applies at.
            attitude: body to ECI, W X Y Z.
            position: m, body position in ECI.
            velocity: m/s, body velocity in ECI.
        """

    def step(self, t: float) -> tuple[Any, Any]:
        """Writes the fixed state.

        Args:
            t: s, the time.

        Returns:
            No output, and the state: m and m/s in ECI, and the identity attitude.

        Raises:
            ZeroDivisionError: the mock was commanded to fail.
        """
        if self._failing:
            raise ZeroDivisionError("the tick's own bug")
        return named("HarnessMock.MockOutputs")(), named("HarnessMock.MockTelemetry")(
            bodyEciPos=np.array([7.0e6, 0.0, 0.0]),
            bodyEciVel=np.array([0.0, 7.5e3, 0.0]),
            bodyEciAttitude=np.array([1.0, 0.0, 0.0, 0.0]),
        )


def parameters(scenario: Any) -> Any:
    """The mock's parameters for one case: its gain is the scenario's Earth `mu`.

    Args:
        scenario: the case's dispersed scenario.

    Returns:
        The parameters, which the ground writes as the case's record.
    """
    return named("HarnessMock.MockParameters")(gain=scenario.mu_m3_s2["earth"])
