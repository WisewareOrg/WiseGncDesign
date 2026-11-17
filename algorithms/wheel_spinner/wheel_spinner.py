# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: active,-all
#     notebook_metadata_filter: -jupytext.text_representation,-kernelspec
# ---

# %% [markdown]
# # The wheel spinner
#
# A test controller with no input: each step it commands one constant motor torque on a reaction
# wheel, so the wheel keeps spinning up. It proves the actuator path, from the GNC's wheel command
# through both edges to Basilisk's wheel.


# %%
"""The wheel spinner: one constant motor torque on the first wheel, every step."""

import numpy as np

from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import read
from fsw.codegen.fpp_types import Gnc
from harness.mission import Mission, mission_tests

__all__ = ["WheelSpinner"]

# %load_ext wise_dynamics.notebook


# %% [markdown]
# ## The wheel's spin momentum
#
# A balanced wheel spinning at $\Omega$ relative to the hub, about the spin axis $\hat{g}_s$, on a
# hub turning at $\omega_{BN}$, carries the spin-axis angular momentum
#
# $$H_s = J_s\,(\Omega + \hat{g}_s \cdot \omega_{BN}),$$
#
# with $J_s$ the wheel's spin inertia. The motor torque $u_s$ is the only torque about the spin
# axis on a frictionless wheel, so
#
# $$\dot H_s = u_s, \qquad H_s(t) = H_s(t_0) + \int_{t_0}^{t} u_s\,d\tau.$$
#
# The spinner's torque is constant from its first step, so the spin momentum grows by $u_s$ times
# the time since then. The hub turns the other way as the wheel spins up, which moves $\Omega$
# itself away from $u_s t / J_s$, but not $H_s$.
#
# The wheel's size and limits are the vehicle's: WiseDynamics' `imu_wheel_spacecraft` carries one
# Honeywell HR16 from Basilisk's `rwFactory`, and its docstring gives them. For the HR16 as that
# vehicle builds it at WiseDynamics a6195a6, $J_s$ is its 50 N·m·s maximum momentum over its
# 6000 rpm maximum speed, about 0.08 kg·m², so a torque of 1 mN·m, far inside its 0.2 N·m limit,
# adds 5.7 N·m·s over 5700 s, about 72 rad/s, far inside its 628 rad/s limit.


# %% [markdown]
# ## Interface
#
# The spinner plays the F´ instance `spinner`. Its contract is `WheelSpinner.fpp` beside this
# notebook: it has no input port, so `step` takes only the time, and returns a
# `Gnc.WheelSpinnerOutputs`, the command on `wheelOut` as a `Gnc.WheelCommand`, and a
# `Gnc.WheelSpinnerTelemetry`, the commanded torque on the channel `wheelTorque`. Its one
# parameter, `motorTorque`, is the torque in N·m on the first of the command's wheels; the rest are
# zero. The command's length is read from the contract, as `WHEELS`.


# %%
WHEELS = next(
    member.size
    for member in read(contract_files()).types["Gnc.WheelCommand"].members
    if member.name == "motorTorque"
)
"""The wheels a `Gnc.WheelCommand` commands: its `motorTorque` array's length in the contract."""


class WheelSpinner:
    """Commands one constant motor torque on the first wheel at every step."""

    def __init__(self, parameters: Gnc.WheelSpinnerParameters) -> None:
        """Holds the command its parameter gives.

        Args:
            parameters: `motorTorque`, N*m, the torque on the first wheel.
        """
        self._torque = float(parameters.motorTorque)
        motor_torque = np.zeros(WHEELS)
        motor_torque[0] = self._torque
        self._command = Gnc.WheelCommand(motorTorque=motor_torque)

    def step(self, t: float) -> tuple[Gnc.WheelSpinnerOutputs, Gnc.WheelSpinnerTelemetry]:
        """Sends the command and writes its torque.

        Args:
            t: s, the time.

        Returns:
            The command on `wheelOut`, and the telemetry `wheelTorque`, N*m, the first wheel's
            torque.
        """
        return Gnc.WheelSpinnerOutputs(wheelOut=self._command), Gnc.WheelSpinnerTelemetry(
            wheelTorque=self._torque
        )


# %% [markdown]
# ## The flight software
#
# `parameters` gives the spinner's parameter for a case, the same whatever the scenario, and the
# ground writes it as the case's record. The `WheelSpinning` configuration's GNC sub-topology flies
# the spinner alone as `spinner`, every base tick, and a mission finds `WheelSpinner` and
# `parameters` here by the component's name. The component has no F´ implementation, no
# `CMakeLists.txt` beside its `.fpp`, so the F´ build leaves the configuration out and it flies on
# the Python build only.


# %%
def parameters(scenario: object) -> Gnc.WheelSpinnerParameters:
    """The spinner's parameter for one case: 1 mN*m on the first wheel.

    Args:
        scenario: the case's dispersed scenario, which does not change it.

    Returns:
        The parameter, which the ground writes as the case's record.
    """
    return Gnc.WheelSpinnerParameters(motorTorque=1e-3)


# %% [markdown]
# ## The mission
#
# The spinner on the wheel spacecraft, flown on the Python build through the scenario the
# requirements tree names, which sets its duration and case count, and judged by `just judge` on
# the wheel momentum rung: the wheel's spin-axis momentum in truth against the integral of the
# torque the spinner wrote.


# %%
MISSION = Mission(
    vehicle="imu_wheel_spacecraft",
    gnc="WheelSpinning",
    build="python",
    rungs=("SRS006",),
    scenarios=("TST003",),
)

# %%
# %%monte_carlo
globals().update(mission_tests(MISSION))


# %% [markdown]
# ## The verdict
#
# The cells below run in the notebook only: the judged rung and its plot.


# %% active="ipynb"
# from harness.notebook import judge, plots
#
# judge()

# %% active="ipynb"
# plots("SRS006")
