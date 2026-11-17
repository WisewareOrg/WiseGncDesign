"""LabBusDriver forwards each role's bus bytes to its typed bus port; an undeliverable push raises.

On a booted copy of the deployment, for every sensor role a configuration takes: the role's
message steps without an assert on its LabBusDriver port, and bytes of the wrong length, a port
nothing is wired to, a port past LabBusDriver's `busOut` and an empty push each trip F´'s own
assert, which raises in Python. Back the other way, a step returns the bytes its GNC sent each
actuator role's `busIn` port that step, once, flown on the test mock `MockActuation`. Skipped
without the deployment `just fsw` builds, as the `fsw` and `bus_by_role` fixtures skip.
"""

import functools
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from fsw.codegen import fpp_types
from fsw.codegen.deployment import bus_port, configuration_model, contract_files
from fsw.codegen.fpp_model import read
from fsw.codegen.roles import taken
from fsw.mock import MOCK
from fsw.mock.actuator.actuator import Actuator
from fsw.python.cdh import outputs
from fsw.python.rio.messages import commands
from ground import parameters
from lab import built, dictionary_path
from lab.bus_emulator import serialize
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


def test_each_step_returns_the_bytes_its_gnc_sent_each_actuator_port_once(tmp_path: Path) -> None:
    """MockActuation's command reaches `busIn` each step, and each step returns that step's alone.

    The bytes are the bus struct F´ serializes for the command, as the Python build's CDH-out and
    RIO-out make it and the bus emulator writes it, on the port the deployment wires the role to.

    Args:
        tmp_path: where the case's record and `.dat` are written.
    """
    configuration = "MockActuation"
    if not built(configuration):
        pytest.skip(f"the F´ build of {configuration} is absent; run `just fsw`")
    fpp_types.load(MOCK)
    [role] = taken(configuration_model(configuration, contract=MOCK), configuration)
    pairs = outputs.pairings([role])
    sent = Actuator(None).step(0.0)[0]
    command = commands(pairs, outputs.convert(pairs, {role.output: sent[0]}))[role.role]
    expected = [(bus_port(configuration, role.output, contract=MOCK), serialize(command))]
    record = tmp_path / "run_0000.prm.json"
    record.write_text('{"MockActuation.actuator": {}}')
    fsw = power_cycle(configuration)
    fsw.boot(str(parameters.dat(record, dictionary_path(configuration)).resolve()), [])

    assert fsw.step(t_ns=NS, bus=[]) == expected
    assert fsw.step(t_ns=2 * NS, bus=[]) == expected
