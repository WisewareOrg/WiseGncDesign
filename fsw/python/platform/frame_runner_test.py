"""The Python build's frame runner, on the deployment's GNC sub-topology with a stub algorithm.

The stub is named for the sub-topology's component, so the frame runner wires it in the
component's place; it logs what it is given and writes what each test needs.
"""

from pathlib import Path

import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fpp_types import Gnc
from fsw.python import FrameRunner

LOG: list[tuple] = []
"""Each call the stub received, in order."""


class ImuDeadReckoner:
    """A stub in the dead reckoner's place: it logs its parameters, steps and commands."""

    def __init__(self, parameters: Gnc.ImuDeadReckonerParameters) -> None:
        """Logs its parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        LOG.append(("boot", parameters))

    def initNavState(
        self, epoch: float, attitude: np.ndarray, position: np.ndarray, velocity: np.ndarray
    ) -> Gnc.ImuDeadReckonerTelemetry:
        """Refuses a negative epoch; otherwise logs it and writes `navState`.

        Args:
            epoch: s, the epoch.
            attitude: (4,) the attitude.
            position: (3,) m, the position.
            velocity: (3,) m/s, the velocity.

        Returns:
            `navState`, `initialized`.

        Raises:
            ValueError: the epoch is negative.
        """
        if epoch < 0.0:
            raise ValueError(f"epoch {epoch} is negative")
        LOG.append(("initNavState", epoch))
        return Gnc.ImuDeadReckonerTelemetry(navState="initialized")

    def step(
        self, t: float, imu: Gnc.ImuReading
    ) -> tuple[Gnc.ImuDeadReckonerOutputs, Gnc.ImuDeadReckonerTelemetry]:
        """Logs the step and writes the reading's rate as the position.

        Args:
            t: s, the time.
            imu: the IMU's reading.

        Returns:
            No output, and `bodyEciPos`.
        """
        LOG.append(("step", t, imu))
        position = np.array(imu.angVelPlatform)
        return Gnc.ImuDeadReckonerOutputs(), Gnc.ImuDeadReckonerTelemetry(bodyEciPos=position)


def _imu(rate: list[float]) -> messaging.IMUSensorMsgPayload:
    """An IMU payload, as the host gives it.

    Args:
        rate: rad/s, its angular velocity.

    Returns:
        The payload.
    """
    payload = messaging.IMUSensorMsgPayload()
    payload.AngVelPlatform = rate
    payload.AccelPlatform = [0.0, 0.0, 9.0]
    return payload


@pytest.fixture
def runner(prm_record: Path) -> FrameRunner:
    """The dead reckoner's configuration, flown with the stub, booted, the log cleared.

    Args:
        prm_record: the case's parameter record.

    Returns:
        The frame runner.
    """
    LOG.clear()
    runner = FrameRunner("ImuDeadReckoning", prm_record, (ImuDeadReckoner,))
    runner.boot()
    return runner


def test_the_frame_runner_is_the_configuration_s_build(runner: FrameRunner):
    """Its period is the FPP base tick, its dictionary the sub-topology's, its build its name.

    Args:
        runner: the frame runner.
    """
    assert runner.period_s == 1.0
    assert runner.build == {"host": "fsw.python.FrameRunner"}
    assert "navState" in runner.dictionary.entries("nav")["channels"]


def test_boot_builds_each_algorithm_afresh_on_its_record_parameters(runner: FrameRunner):
    """Each boot is a power cycle: a new algorithm on the parameters the case's record holds.

    Args:
        runner: the frame runner.
    """
    [(_, parameters)] = LOG
    assert type(parameters) is Gnc.ImuDeadReckonerParameters
    np.testing.assert_array_equal(parameters.dcm_PB, np.zeros((3, 3)))

    runner.boot()

    assert [entry[0] for entry in LOG] == ["boot", "boot"]


def test_a_tick_converts_the_message_steps_at_its_time_and_commands_nothing(
    runner: FrameRunner,
):
    """The IMU's payload reaches the step as a `Gnc.ImuReading` at `t` in s; RIO-out is empty.

    Args:
        runner: the frame runner.
    """
    commands = runner.tick(2_000_000_000, {"imu": _imu([1.0, 2.0, 3.0])})

    assert commands == {}
    [_, (_, t, imu)] = LOG
    assert t == 2.0
    assert isinstance(imu, Gnc.ImuReading)
    np.testing.assert_array_equal(imu.angVelPlatform, [1.0, 2.0, 3.0])
    [(name, t_ns, raw)] = runner.telemetry()
    assert (name, t_ns) == ("nav.bodyEciPos", 2_000_000_000)
    np.testing.assert_array_equal(runner.values(name, [raw]), [[1.0, 2.0, 3.0]])
    assert runner.telemetry() == []


def test_commands_run_by_name_before_the_step_and_answer_with_f_prime_s_responses(
    runner: FrameRunner,
):
    """Each command uplinked runs at the next tick, before the step, its telemetry tagged then.

    Args:
        runner: the frame runner.
    """
    vector = np.zeros(3)
    args = {"attitude": np.array([1.0, 0, 0, 0]), "position": vector, "velocity": vector}
    runner.uplink("nav.initNavState", {"epoch": 0.5, **args}, 7)
    runner.uplink("nav.initNavState", {"epoch": -1.0, **args}, 8)
    runner.uplink("nav.MU_PRM_SET", {"val": 1.0}, 9)
    runner.uplink("nav.reset", {}, 10)
    assert runner.responses() == []

    runner.tick(1_000_000_000, {"imu": _imu([0.0, 0.0, 0.0])})

    assert [entry[0] for entry in LOG] == ["boot", "initNavState", "step"]
    assert runner.responses() == [
        (7, "OK", None),
        (8, "VALIDATION_ERROR", "epoch -1.0 is negative"),
        (9, "INVALID_OPCODE", None),
        (10, "INVALID_OPCODE", None),
    ]
    assert runner.responses() == []
    assert [(name, t_ns) for name, t_ns, _ in runner.telemetry()] == [
        ("nav.navState", 1_000_000_000),
        ("nav.bodyEciPos", 1_000_000_000),
    ]


def test_a_vehicle_without_the_configuration_s_role_fails_the_tick_naming_it(
    runner: FrameRunner,
):
    """The configuration takes the IMU; a vehicle with no IMU message fails the tick.

    Args:
        runner: the frame runner.
    """
    with pytest.raises(KeyError, match="imu"):
        runner.tick(1_000_000_000, {})
