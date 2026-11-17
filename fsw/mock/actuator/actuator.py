"""The test mock `MockGnc.Actuator`, as an algorithm's notebook gives it: its C++'s Python twin."""

from typing import Any

import numpy as np

from fsw.codegen.fpp_types import named


class Actuator:
    """Sends one fixed wheel command at every step, as `Actuator.cpp` does: element i (i + 1) mN*m.

    The command stays inside a wheel's torque limit, so a flight checks the command, not the clamp.
    """

    def __init__(self, parameters: Any) -> None:
        """Keeps nothing: it has no parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """

    def step(self, t: float) -> tuple[Any, Any]:
        """Sends the command.

        Args:
            t: s, the time.

        Returns:
            The command on `wheelOut`, element i (i + 1) mN*m, and no telemetry.
        """
        command = named("Gnc.WheelCommand")(motorTorque=np.arange(1, 37) * 1e-3)
        return named("MockGnc.ActuatorOutputs")(wheelOut=command), named(
            "MockGnc.ActuatorTelemetry"
        )()
