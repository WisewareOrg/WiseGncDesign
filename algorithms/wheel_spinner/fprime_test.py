"""The F´ build of the wheel spinner against the notebook's, step for step.

Skipped without the deployment `just fsw` builds.
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

from algorithms.wheel_spinner.wheel_spinner import WheelSpinner
from fsw.codegen.deployment import bus_port, configuration_model
from fsw.codegen.fpp_types import Gnc
from fsw.codegen.roles import taken
from fsw.python.cdh import outputs
from fsw.python.rio.messages import commands
from ground.fprime_station import FprimeStation
from lab import built
from lab.bus_emulator import serialize

if not built("WheelSpinning"):
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

NS = 1_000_000_000
"""ns per s."""

SPINNER = Gnc.WheelSpinnerParameters(motorTorque=2.5e-3)
"""The spinner's parameter: a torque other than the notebook's case value."""


@pytest.fixture(scope="session")
def configuration() -> str:
    """The spinner's configuration, the only one this module's cases fly.

    Returns:
        `WheelSpinning`.
    """
    return "WheelSpinning"


@pytest.fixture
def case_parameters(case_parameters: dict[str, Any]) -> dict[str, Any]:
    """The deployment's case parameters, the spinner's tuple replaced by `SPINNER`.

    Args:
        case_parameters: the deployment's, each zero, as the root conftest gives them.

    Returns:
        Each instance's tuple, by its qualified name.
    """
    return {
        instance: SPINNER if type(t) is type(SPINNER) else t
        for instance, t in case_parameters.items()
    }


def test_each_step_sends_the_notebook_s_command_and_writes_its_torque(
    configuration: str,
    booted: ModuleType,
    station: FprimeStation,
    decoded: Callable[[Any], list[tuple[str, int, Any]]],
) -> None:
    """Booted on the record's torque, each step returns the wheel bytes the Python build makes.

    The bytes are the bus struct the notebook's command becomes through the Python build's
    CDH-out and RIO-out, on the port the deployment wires the wheel role to; each step also
    writes `spinner.wheelTorque`, the record's torque, at the step's time.

    Args:
        configuration: the spinner's configuration.
        booted: the test's copy of the deployment, booted on the case's parameters.
        station: the station on it.
        decoded: drains the station's telemetry as values.
    """
    [role] = taken(configuration_model(configuration), configuration)
    pairs = outputs.pairings([role])
    sent = WheelSpinner(SPINNER).step(0.0)[0]
    command = commands(pairs, outputs.convert(pairs, {role.output: sent.wheelOut}))[role.role]
    expected = [(bus_port(configuration, role.output), serialize(command))]

    for k in (1, 2, 3):
        assert booted.step(t_ns=k * NS, bus=[]) == expected

    writes = [(n, t, v) for n, t, v in decoded(station) if n.startswith("spinner.")]
    assert writes == [("spinner.wheelTorque", k * NS, SPINNER.motorTorque) for k in (1, 2, 3)]
