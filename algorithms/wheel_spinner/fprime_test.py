"""The F´ build of the wheel spinner against the notebook's, step for step.

Skipped without the deployment `just fsw` builds.
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any

from algorithms.wheel_spinner.wheel_spinner import WheelSpinner
from fsw.codegen.deployment import bus_port, configuration_model
from fsw.codegen.fpp_types import Gnc
from fsw.codegen.roles import Role, taken
from ground.fprime_station import FprimeStation
from lab.bus_emulator import serialize

CONFIGURATION = "WheelSpinning"
"""The spinner's configuration, the only one this module's cases fly."""

NS = 1_000_000_000
"""ns per s."""

SPINNER = Gnc.WheelSpinnerParameters(motorTorque=2.5e-3)
"""The spinner's parameter: a torque other than the notebook's case value."""


def test_each_step_sends_the_notebook_s_command_and_writes_its_torque(
    boot: Callable[..., tuple[ModuleType, FprimeStation]],
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
    python_command: Callable[[Role, Any], Any],
) -> None:
    """Booted on the record's torque, each step returns the wheel bytes the Python build makes.

    The bytes are the bus struct the notebook's command becomes through the Python build's
    CDH-out and RIO-out, on the port the deployment wires the wheel role to; each step also
    writes `spinner.wheelTorque`, the record's torque, at the step's time.

    Args:
        boot: boots the configuration on the parameters given.
        decoded: drains the station's telemetry as values.
        python_command: gives the Python build's command for a role.
    """
    fsw, station = boot(CONFIGURATION, {f"{CONFIGURATION}.spinner": SPINNER})
    [role] = taken(configuration_model(CONFIGURATION), CONFIGURATION)
    sent, _ = WheelSpinner(SPINNER).step(0.0)
    command = python_command(role, sent.wheelOut)
    expected = [(bus_port(CONFIGURATION, role.output), serialize(command))]

    for k in (1, 2, 3):
        assert fsw.step(t_ns=k * NS, bus=[]) == expected

    writes = [(n, t, v) for n, t, v in decoded(station) if n.startswith("spinner.")]
    assert writes == [("spinner.wheelTorque", k * NS, SPINNER.motorTorque) for k in (1, 2, 3)]
