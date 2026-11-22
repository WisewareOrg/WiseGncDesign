"""The wheel spinner's tests: its contract, its constant command and its case's parameters."""

from pathlib import Path

import pytest

from algorithms.wheel_spinner.wheel_spinner import WHEELS, WheelSpinner, parameters
from fsw.codegen.fpp_types import Gnc
from harness.notebook import run_notebook
from lab import built


@pytest.mark.parametrize("t", [0.0, 1.0, 5700.0])
def test_each_step_commands_the_parameter_s_torque_on_the_first_wheel_alone_and_writes_it(t: float):
    """Element 0 of `wheelOut` is `motorTorque`, every other element zero, at any time.

    Args:
        t: s, the step's time.
    """
    spinner = WheelSpinner(Gnc.WheelSpinnerParameters(motorTorque=2.5e-3))

    outputs, telemetry = spinner.step(t)

    motor_torque = outputs.wheelOut.motorTorque
    assert motor_torque.shape == (WHEELS,)
    assert motor_torque[0] == 2.5e-3
    assert not motor_torque[1:].any()
    assert telemetry == Gnc.WheelSpinnerTelemetry(wheelTorque=2.5e-3)


def test_a_case_s_parameters_command_one_millinewton_metre() -> None:
    """`parameters` gives `motorTorque` 1e-3 N*m whatever the scenario."""
    assert parameters(None) == Gnc.WheelSpinnerParameters(motorTorque=1e-3)


def test_the_notebook_runs_end_to_end() -> None:
    """Every cell of the algorithm notebook runs, the notebook-only cells included."""
    run_notebook(Path(__file__).with_name("wheel_spinner.py"))


def test_the_parity_notebook_runs_end_to_end() -> None:
    """Every cell of the parity notebook runs, so the two builds agree on a twin per scenario."""
    if not built("WheelSpinning"):
        pytest.skip("the F´ build is absent; run `just fsw`")
    run_notebook(Path(__file__).with_name("parity.py"))
