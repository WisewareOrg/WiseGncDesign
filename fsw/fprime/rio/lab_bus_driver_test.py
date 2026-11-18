"""LabBusDriver forwards each role's bus bytes to its typed bus port; an undeliverable push raises.

On a booted copy of the deployment, for every role of the contract's `Cdh.BusConverter`: the
role's message steps without an assert on its LabBusDriver port, and bytes of the wrong length, a
port nothing is wired to, a port past LabBusDriver's `busOut` and an empty push each trip F´'s own
assert, which raises in Python. Skipped without the deployment `just fsw` builds, as the `fsw` and
`bus_by_role` fixtures skip.
"""

import functools
from collections.abc import Callable
from types import ModuleType

import pytest

from fsw.codegen.deployment import contract_files
from fsw.codegen.fpp_model import read
from lab.power_cycle import power_cycle

NS = 1_000_000_000
"""ns per s."""

_DRIVER = r'^Assert: "[^"]*fsw/fprime/rio/LabBusDriver\.cpp:\d+"'
"""The assert LabBusDriver's own leftover-bytes check raises."""

_TOPOLOGY = r'^Assert: "[^"]*FswTopologyAc\.cpp:\d+"'
"""An assert the deployment's generated port calls raise: an unknown port, or bytes too short."""


@functools.cache
def _bus_out_ports() -> int:
    """The size of LabBusDriver's `busOut`, read from its FPP.

    Returns:
        The number of ports.
    """
    outputs = read(contract_files()).components["Bus.LabBusDriver"].outputs
    [bus_out] = [port for port in outputs if port.name == "busOut"]
    return bus_out.size


def _stepped(
    configuration: str, prm: str, parameter_ids: list[int], port: int, data: bytes
) -> ModuleType:
    """A fresh copy, booted and stepped once on a role's own message on its port.

    A copy that raised is never reused, so each refused push flies its own copy, and the clean
    step first shows the port delivers, so a later raise comes from the push under test.

    Args:
        configuration: the configuration power-cycled.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        port: the role's LabBusDriver port.
        data: the role's message bytes.

    Returns:
        The copy.
    """
    fsw = power_cycle(configuration)
    fsw.boot(prm, parameter_ids)
    fsw.step(t_ns=NS, bus=[(port, data)])
    return fsw


def test_every_role_s_bus_message_steps_without_an_assert(
    booted: ModuleType, bus: list[tuple[int, bytes]]
) -> None:
    """Every role's message, as the bus emulator writes it, steps the deployment on its port.

    The values' proof is elsewhere: the bus emulator's test from #62 CDH generator, F´ half, the
    `cdh_<role>` pin test, and an algorithm's own F´ test plus the F´ campaign, reading for
    reading.

    Args:
        booted: the test's copy of the deployment, booted idle on the case's parameters.
        bus: every role's bus message on its LabBusDriver port.
    """
    assert bus

    booted.step(t_ns=NS, bus=bus)


@pytest.mark.parametrize(
    ("push", "source"),
    [
        (lambda port, data, unwired: (port, data[:-1]), _TOPOLOGY),
        (lambda port, data, unwired: (port, data + bytes(1)), _DRIVER),
        (lambda port, data, unwired: (unwired[0], data), _TOPOLOGY),
        (lambda port, data, unwired: (_bus_out_ports(), data), _TOPOLOGY),
        (lambda port, data, unwired: (port, b""), _TOPOLOGY),
    ],
    ids=["one-short", "one-over", "unwired-port", "port-past-busOut", "empty"],
)
def test_a_push_lab_bus_driver_cannot_deliver_raises(
    configuration: str,
    prm: str,
    parameter_ids: list[int],
    bus_by_role: dict[str, tuple[int, bytes]],
    push: Callable[[int, bytes, list[int]], tuple[int, bytes]],
    source: str,
) -> None:
    """Each role's push that LabBusDriver cannot deliver trips F´'s assert in Python.

    One short of the role's message fails the connected port's deserialization, and one over
    fails LabBusDriver's check that the port consumed every byte. The message on a port nothing is
    wired to, or past `busOut`, or no bytes, fail the deployment's generated port call.

    Args:
        configuration: the configuration.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus_by_role: each role's LabBusDriver port and message bytes.
        push: the push refused, from the role's port and bytes and the unwired ports.
        source: the assert expected, by its file.
    """
    assert bus_by_role
    unwired = sorted(set(range(_bus_out_ports())) - {port for port, _ in bus_by_role.values()})
    assert unwired, "every LabBusDriver port is wired"
    for port, data in bus_by_role.values():
        fsw = _stepped(configuration, prm, parameter_ids, port, data)

        with pytest.raises(RuntimeError, match=source):
            fsw.step(t_ns=2 * NS, bus=[push(port, data, unwired)])
