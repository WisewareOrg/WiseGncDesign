"""SimHub delivers each role's bus bytes to the typed bus port, and wrong-length bytes raise.

On a booted copy of the deployment, for every role of the contract's `Cdh.BusConverter`: F´
deserializes the bytes pushed on the role's SimHub port into the bus struct the port connects to,
and a push of the wrong length trips F´'s own assert, which raises in Python. Skipped without the
deployment `just fsw` builds, as the `fsw` and `bus_by_role` fixtures skip.
"""

from types import ModuleType

import pytest

from lab.power_cycle import power_cycle

NS = 1_000_000_000
"""ns per s."""


def test_every_role_s_bus_message_steps_cleanly_on_its_port(
    fsw: ModuleType, prm: str, parameter_ids: list[int], bus: list[tuple[int, bytes]]
) -> None:
    """Every role's message, as the bus emulator writes it, steps the deployment on its port.

    Args:
        fsw: a copy of the deployment.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its SimHub port.
    """
    assert bus
    fsw.boot(prm, parameter_ids)

    fsw.step(t_ns=NS, bus=bus)


@pytest.mark.parametrize("change", [-1, 1], ids=["one-short", "one-over"])
def test_a_role_s_push_of_the_wrong_length_raises(
    prm: str,
    parameter_ids: list[int],
    bus_by_role: dict[str, tuple[int, bytes]],
    change: int,
) -> None:
    """Each role's bytes one short of its message, or one over, trip F´'s assert in Python.

    Each role's push flies a fresh copy, since a copy that raised is never reused. The copy first
    steps on the role's own message on that port, so the raise comes from the length, not the port.

    Args:
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus_by_role: each role's SimHub port and message bytes.
        change: the bytes added to the message, or removed from it.
    """
    assert bus_by_role
    for port, data in bus_by_role.values():
        fsw = power_cycle()
        fsw.boot(prm, parameter_ids)
        fsw.step(t_ns=NS, bus=[(port, data)])
        wrong = data[:change] if change < 0 else data + bytes(change)

        with pytest.raises(RuntimeError, match=r'^Assert: ".*:\d+"'):
            fsw.step(t_ns=2 * NS, bus=[(port, wrong)])
