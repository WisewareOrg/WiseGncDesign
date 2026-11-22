"""LabBusDriver forwards each role's bus bytes to its typed bus port; an undeliverable push raises.

On a booted copy of the deployment, for every sensor role a configuration takes: the role's
message steps without an assert on its LabBusDriver port, and bytes of the wrong length, a port
nothing is wired to, a port past LabBusDriver's `busOut` and an empty push each trip F´'s own
assert, which raises in Python. Back the other way, a step returns the bytes its GNC sent each
actuator role's `busIn` port that step, once, flown on the test mock `MockActuation`. Skipped
without the deployment `just fsw` builds, as the `fsw` and `bus_by_role` fixtures skip.
"""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from fsw.codegen.deployment import bus_port, configuration_model
from fsw.codegen.roles import Role, taken
from fsw.mock import MOCK
from lab.bus_emulator import serialize

NS = 1_000_000_000
"""ns per s."""

_DRIVER = r'^Assert: "[^"]*fsw/fprime/rio/LabBusDriver\.cpp:\d+"'
"""The assert LabBusDriver's own leftover-bytes check raises."""

_TOPOLOGY = r'^Assert: "[^"]*FswTopologyAc\.cpp:\d+"'
"""An assert the deployment's generated port calls raise: bytes too short."""


@pytest.mark.parametrize(
    ("push", "source"),
    [
        (lambda port, data: (port, data[:-1]), _TOPOLOGY),
        (lambda port, data: (port, data + bytes(1)), _DRIVER),
    ],
    ids=["one-short", "one-over"],
)
def test_a_push_lab_bus_driver_cannot_deliver_raises(
    configuration: str,
    boot: Callable[..., tuple[ModuleType, Any]],
    bus_by_role: dict[str, tuple[int, bytes]],
    push: Callable[[int, bytes], tuple[int, bytes]],
    source: str,
) -> None:
    """Each role's push that LabBusDriver cannot deliver trips F´'s assert in Python.

    One short of the role's message fails the connected port's deserialization, and one over
    fails LabBusDriver's check that the port consumed every byte. A copy that raised is never
    reused, so each refused push flies a copy of its own, and the clean step first shows the port
    delivers, so a later raise comes from the push under test.

    Args:
        configuration: the configuration.
        boot: boots the configuration.
        bus_by_role: each role's LabBusDriver port and message bytes.
        push: the push refused, from the role's port and bytes.
        source: the assert expected, by its file.
    """
    if not bus_by_role:
        pytest.skip(f"{configuration} takes no sensor role")
    for port, data in bus_by_role.values():
        fsw, _ = boot(configuration)
        fsw.step(t_ns=NS, bus=[(port, data)])

        with pytest.raises(RuntimeError, match=source):
            fsw.step(t_ns=2 * NS, bus=[push(port, data)])


def test_a_step_in_which_gnc_sends_no_actuator_command_returns_none(
    booted: ModuleType, fprime_configuration: str, bus: list[tuple[int, bytes]]
) -> None:
    """A configuration taking no actuator role drains nothing from LabBusDriver's `busIn`.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        fprime_configuration: the configuration.
        bus: every sensor role's bus message on its LabBusDriver port.
    """
    roles = taken(configuration_model(fprime_configuration), fprime_configuration)
    if any(not role.sensor for role in roles):
        pytest.skip(f"{fprime_configuration} takes an actuator role")

    assert booted.step(t_ns=NS, bus=bus) == []
    assert booted.step(t_ns=2 * NS, bus=bus) == []


def test_each_step_returns_the_bytes_its_gnc_sent_each_actuator_port_once(
    mock_actuation: tuple[str, Role, Any, Path], boot: Callable[..., tuple[ModuleType, Any]]
) -> None:
    """MockActuation's command reaches `busIn` each step, and each step returns that step's alone.

    The bytes are the bus struct F´ serializes for the command, as the Python build's CDH-out and
    RIO-out make it and the bus emulator writes it, on the port the deployment wires the role to.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
        boot: boots the configuration.
    """
    configuration, role, command, _ = mock_actuation
    expected = [(bus_port(configuration, role.output, contract=MOCK), serialize(command))]
    fsw, _ = boot(configuration)

    assert fsw.step(t_ns=NS, bus=[]) == expected
    assert fsw.step(t_ns=2 * NS, bus=[]) == expected
