"""The judge's test mock, as an algorithm's notebook gives it: its class alone."""

from typing import Any

import numpy as np

from fsw.codegen.fpp_types import named


class NavMock:
    """Writes the nav role's estimate channels with a fixed state at every step."""

    def __init__(self, parameters: Any) -> None:
        """Takes its empty parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """

    def step(self, t: float) -> tuple[Any, Any]:
        """Writes the fixed state.

        Args:
            t: s, the time.

        Returns:
            No output, and the state: m and m/s in ECI, and the identity attitude.
        """
        return named("HarnessMock.NavMockOutputs")(), named("HarnessMock.NavMockTelemetry")(
            bodyEciPos=np.array([7.0e6, 0.0, 0.0]),
            bodyEciVel=np.array([0.0, 7.5e3, 0.0]),
            bodyEciAttitude=np.array([1.0, 0.0, 0.0, 0.0]),
        )
