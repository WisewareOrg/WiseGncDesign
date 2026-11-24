"""The test mock `MockGnc.Actuator`, as an algorithm's notebook gives it: its C++'s Python twin."""

from typing import Any

import numpy as np

from fsw.codegen.fpp_types import named


class Actuator:
    """Counts each step and mark, and sends one fixed wheel command at every step, as `Actuator.cpp` does.

    The command's element i is (i + 1) mN*m.

    The command stays inside a wheel's torque limit, so a flight checks the command, not the clamp.
    """

    def __init__(self, parameters: Any) -> None:
        """Starts the tally at 0; it has no parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        self._tally = 0

    def mark(self) -> Any:
        """Counts one.

        Returns:
            The tally, written.
        """
        self._tally += 1
        return named("MockGnc.ActuatorTelemetry")(tally=self._tally)

    def allocate(self) -> None:
        """Does nothing: the Python build has no allocator."""

    def step(self, t: float) -> tuple[Any, Any]:
        """Sends the command.

        Args:
            t: s, the time.

        Returns:
            The command on `wheelOut`, element i (i + 1) mN*m, and the tally, written.
        """
        self._tally += 1
        command = named("Gnc.WheelCommand")(motorTorque=np.arange(1, 37) * 1e-3)
        return named("MockGnc.ActuatorOutputs")(wheelOut=command), named("MockGnc.ActuatorTelemetry")(tally=self._tally)
