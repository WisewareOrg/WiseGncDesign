"""LabBusDriver moves bus bytes through fixed buffers made at boot; an undeliverable push raises.

On a booted copy of the deployment, for every sensor role a configuration takes: a receive buffer
one byte short of the role's message, and one over, each trip F´'s own assert at the step, which
raises in Python, and a buffer is made only before the first step, once per port. Back the other
way, each step returns which transmit buffers its GNC wrote, holding the bytes it sent, flown on the
test mock `MockActuation`; bytes of another size than a port's transmit buffer, or for a port with
none, trip F´'s assert. Skipped without the deployment `just fsw` builds, as the `boot` and
`bus_by_role` fixtures skip.
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
"""An assert LabBusDriver's own checks raise."""

_TOPOLOGY = r'^Assert: "[^"]*FswTopologyAc\.cpp:\d+"'
"""An assert the deployment's generated port calls raise: bytes too short."""


@pytest.mark.parametrize(
    ("change", "source"),
    [(lambda data: data[:-1], _TOPOLOGY), (lambda data: data + bytes(1), _DRIVER)],
    ids=["one-short", "one-over"],
)
def test_a_receive_buffer_lab_bus_driver_cannot_deliver_raises_at_the_step(
    configuration: str,
    boot: Callable[..., tuple[ModuleType, Any]],
    wire: Callable[..., Any],
    bus_by_role: dict[str, tuple[int, bytes]],
    change: Callable[[bytes], bytes],
    source: str,
) -> None:
    """Each role's buffer of another size than its message trips F´'s assert in Python.

    One short of the role's message fails the connected port's deserialization, and one over
    fails LabBusDriver's check that the port consumed every byte. A copy that raised is never
    reused, so each flies a copy of its own; a copy whose buffer fits steps first, so the raise
    comes from the size under test.

    Args:
        configuration: the configuration.
        boot: boots the configuration.
        wire: steps a copy on a bus.
        bus_by_role: each role's LabBusDriver port and message bytes.
        change: the buffer's bytes, from the message's.
        source: the assert expected, by its file.
    """
    if not bus_by_role:
        pytest.skip(f"{configuration} takes no sensor role")
    for port, data in bus_by_role.values():
        fits, _ = boot(configuration)
        wire(fits, configuration, [(port, data)])(NS)
        fsw, _ = boot(configuration)
        step = wire(fsw, configuration, [(port, change(data))])

        with pytest.raises(RuntimeError, match=source):
            step(NS)


def test_a_buffer_is_made_once_per_port_and_only_before_the_first_step(
    booted: ModuleType,
    fprime_configuration: str,
    boot: Callable[..., tuple[ModuleType, Any]],
    wire: Callable[..., Any],
) -> None:
    """A second buffer on a port, a port past the driver's, or a buffer after a step raise.

    The buffers made here fit no port's struct, so the step that follows them is another copy's,
    whose actuator roles' transmit buffers fit.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        fprime_configuration: the configuration.
        boot: boots the configuration.
        wire: steps a copy on a bus.
    """
    booted.receive_buffer(0, 8)
    booted.transmit_buffer(0, 8)
    with pytest.raises(RuntimeError, match="port 0 already has a receive buffer"):
        booted.receive_buffer(0, 8)
    with pytest.raises(RuntimeError, match="port 0 already has a transmit buffer"):
        booted.transmit_buffer(0, 8)
    with pytest.raises(IndexError, match="port 8 is past LabBusDriver's 8"):
        booted.receive_buffer(8, 8)
    with pytest.raises(IndexError, match="port -1 is past LabBusDriver's 8"):
        booted.transmit_buffer(-1, 8)

    stepped, _ = boot(fprime_configuration)
    wire(stepped, fprime_configuration, [])(NS)

    with pytest.raises(RuntimeError, match="after the first step"):
        stepped.receive_buffer(1, 8)
    with pytest.raises(RuntimeError, match="after the first step"):
        stepped.transmit_buffer(1, 8)


def test_a_receive_buffer_is_writable_and_a_transmit_buffer_is_not(booted: ModuleType) -> None:
    """The lab writes a receive buffer in place and only reads a transmit buffer.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
    """
    receive = booted.receive_buffer(0, 4)
    transmit = booted.transmit_buffer(0, 4)

    receive[:] = b"\x01\x02\x03\x04"

    assert bytes(receive) == b"\x01\x02\x03\x04"
    assert transmit.readonly
    assert not receive.readonly


def test_a_step_in_which_gnc_sends_no_actuator_command_writes_no_transmit_buffer(
    booted: ModuleType, fprime_configuration: str, bus: list[tuple[int, bytes]], wire: Callable[..., Any]
) -> None:
    """A configuration taking no actuator role writes no transmit buffer.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        fprime_configuration: the configuration.
        bus: every sensor role's bus message on its LabBusDriver port.
        wire: steps a copy on a bus.
    """
    roles = taken(configuration_model(fprime_configuration), fprime_configuration)
    if any(not role.sensor for role in roles):
        pytest.skip(f"{fprime_configuration} takes an actuator role")
    step = wire(booted, fprime_configuration, bus)

    assert step(NS) == 0
    assert step(2 * NS) == 0


def test_each_step_returns_the_transmit_buffers_its_gnc_wrote_holding_the_bytes_sent(
    mock_actuation: tuple[str, Role, Any, Path], boot: Callable[..., tuple[ModuleType, Any]]
) -> None:
    """MockActuation's command lands in its port's transmit buffer, flagged in each step's return.

    The bytes are the bus struct F´ serializes for the command, as the Python build's CDH-out and
    RIO-out make it and the bus emulator writes it, on the port the deployment wires the role to.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
        boot: boots the configuration.
    """
    configuration, role, command, _ = mock_actuation
    port = bus_port(configuration, role.output, contract=MOCK)
    expected = serialize(command)
    fsw, _ = boot(configuration)
    transmit = fsw.transmit_buffer(port, len(expected))

    for k in (1, 2):
        assert fsw.step(k * NS) == 1 << port
        assert bytes(transmit) == expected


@pytest.mark.parametrize("change", [-1, 1, None], ids=["one-short", "one-over", "no-buffer"])
def test_a_command_that_does_not_fit_its_transmit_buffer_raises_at_the_step(
    mock_actuation: tuple[str, Role, Any, Path], boot: Callable[..., tuple[ModuleType, Any]], change: int | None
) -> None:
    """A command of another size than its port's transmit buffer, or on a port with none, raises.

    Args:
        mock_actuation: the configuration, its role, the Python build's command and the record.
        boot: boots the configuration.
        change: bytes added to the command's size, or None for no buffer on its port.
    """
    configuration, role, command, _ = mock_actuation
    port = bus_port(configuration, role.output, contract=MOCK)
    fsw, _ = boot(configuration)
    if change is not None:
        fsw.transmit_buffer(port, len(serialize(command)) + change)

    with pytest.raises(RuntimeError, match=_DRIVER):
        fsw.step(NS)
