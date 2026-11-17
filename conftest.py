"""Fixtures every package's tests share: an F´ copy, its station, a drain, messages, parameters.

A fixture needing the F´ build, or the dictionary it generates, skips its test without it. Every
pytest run loads this file, the judge's included, so the FPP model, Basilisk and F´ are imported
only by the fixtures that need them.
"""

from __future__ import annotations

import importlib.util
import itertools
import operator
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np
import pytest

if TYPE_CHECKING:
    from ground.fprime_station import FprimeStation


@pytest.fixture
def fsw() -> ModuleType:
    """A fresh copy of the deployment, not yet booted; skips the test without the F´ build.

    Returns:
        The copy.
    """
    if importlib.util.find_spec("lab._wise_fsw") is None:
        pytest.skip("the F´ build is absent; run `just fsw`")
    from lab.power_cycle import power_cycle

    return power_cycle()


@pytest.fixture
def station(fsw: ModuleType) -> FprimeStation:
    """The ground station on the test's copy, on the dictionary the build generated.

    Args:
        fsw: the test's copy.

    Returns:
        The station.
    """
    from ground.dictionary import Dictionary
    from ground.fprime_station import FprimeStation
    from lab import DICTIONARY

    return FprimeStation(fsw, Dictionary(DICTIONARY))


@pytest.fixture
def decoded() -> Callable[[Any], list[tuple[str, int, Any]]]:
    """A drain of an edge's telemetry, each write decoded to its value by the edge.

    Returns:
        A function taking an edge, such as an `FprimeStation` or a `lab.FprimeModule`, and giving
        each write since the edge's last drain as `(<instance>.<channel>, time tag in ns, value)`,
        oldest first.
    """

    def drain(edge: Any) -> list[tuple[str, int, Any]]:
        """Drains the edge's telemetry writes, each as its value.

        Args:
            edge: the edge.

        Returns:
            Each write's channel name, time tag in ns and value, oldest first.
        """
        return [(name, t_ns, edge.values(name, [raw])[0]) for name, t_ns, raw in edge.telemetry()]

    return drain


class BusMessage(NamedTuple):
    """A bus struct and a Basilisk message of it.

    Attributes:
        struct: the bus struct, as `fsw.codegen.fpp_model` reads it.
        payload: the Basilisk payload the struct mirrors, its values set.
        values: each member's values by its FPP name, in the struct's order.
    """

    struct: Any
    payload: Any
    values: dict[str, list[Any]]


@pytest.fixture
def bus_messages() -> dict[str, BusMessage]:
    """A message of every bus struct in `lab.bus_emulator.BUS`, every value distinct.

    Each element of each member of each struct takes the next of 0.5, 1.5, 2.5, ..., in its FPP
    type, so a field or element out of place changes the result. Each struct's payload is the
    `messaging.<Name>Payload` it mirrors, matched ignoring case as `bus_test.py` holds them.

    Returns:
        Each struct's message, by its qualified name.
    """
    from Basilisk.architecture import messaging

    from fsw.codegen.fields import DTYPES
    from fsw.codegen.fpp_model import Struct, read
    from lab.bus_emulator import BUS

    payloads = {n.lower(): getattr(messaging, n) for n in dir(messaging) if n.endswith("Payload")}
    counter = itertools.count()
    messages = {}
    for name, struct in read([BUS]).types.items():
        if not (name.startswith("Bus.") and isinstance(struct, Struct)):
            continue
        payload = payloads[name.removeprefix("Bus.").lower() + "payload"]()
        fields = {field.lower(): field for field in type(payload).__dtype__.names}
        values = {}
        for member in struct.members:
            elements = [next(counter) + 0.5 for _ in range(member.size)]
            values[member.name] = np.array(elements, DTYPES[member.type]).tolist()
            setattr(payload, fields[member.name.lower()], values[member.name])
        messages[name] = BusMessage(struct, payload, values)
    return messages


@pytest.fixture
def bus_by_role(bus_messages: dict[str, BusMessage]) -> dict[str, tuple[int, bytes]]:
    """Each role's LabBusDriver port and its bus message's bytes, as the bus emulator writes them.

    The roles are the contract's `Cdh.BusConverter`'s, and each port is the one the built
    deployment's configuration wires to the role's CDH input, read from its FPP. The shared
    deployment template, `fsw/fprime/deployment/Fsw.fpp.in`, wires every role into every
    configuration, so a role left unwired fails the fixture with `bus_port`'s `ValueError`.

    Args:
        bus_messages: a message of each bus struct.

    Returns:
        Each role's `(port, bytes)`, by the role's name.
    """
    from fsw.codegen.deployment import bus_port, contract_files
    from fsw.codegen.fpp_model import read
    from fsw.codegen.roles import roles
    from ground.dictionary import Dictionary
    from lab.bus_emulator import serialize

    instances = Dictionary(_dictionary()).algorithm_instances()
    (configuration,) = {instance.name.split(".", 1)[0] for instance in instances}
    return {
        role.role: (
            bus_port(configuration, role.input),
            serialize(bus_messages[role.bus].payload),
        )
        for role in roles(read(contract_files()))
    }


@pytest.fixture
def bus(bus_by_role: dict[str, tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    """The bus one step takes: every role's message bytes on its LabBusDriver port.

    Args:
        bus_by_role: each role's port and bytes.

    Returns:
        `[(port, bytes)]`, a pair per role.
    """
    return list(bus_by_role.values())


@pytest.fixture(scope="session")
def case_parameters() -> tuple[Any, ...]:
    """Each algorithm instance's parameters in the deployment, every value zero, of its FPP shape.

    The instances are those the deployment's dictionary holds, so the case skips without it. A
    zero holds for a numeric parameter or an array of them; a parameter of an enum, struct or
    string type gets none, and fails `parameters_from` or the `.dat`. A test module flying an
    algorithm's own values overrides this fixture, swapping that algorithm's tuple in.

    Returns:
        Each instance's `<Name>Parameters` tuple.
    """
    from fsw.codegen import fpp_types
    from fsw.codegen.deployment import contract_files
    from fsw.codegen.fpp_model import Array, read
    from ground.dictionary import Dictionary

    model = read(contract_files())
    tuples = []
    for instance in Dictionary(_dictionary()).algorithm_instances():
        component = model.components[instance.component]
        values = {}
        for parameter in component.parameters:
            shape, type_name = (), parameter.type
            while isinstance(array := model.types.get(type_name), Array):
                shape, type_name = (*shape, array.size), array.element
            values[parameter.name] = np.zeros(shape).tolist()
        tuple_type = operator.attrgetter(f"{component.name}Parameters")(fpp_types)
        tuples.append(fpp_types.parameters_from(tuple_type, values))
    return tuple(tuples)


@pytest.fixture
def prm_record(case_parameters: tuple[Any, ...], tmp_path: Path) -> Path:
    """A case's parameter record, written as the ground writes it, in a case directory of its own.

    Args:
        case_parameters: the case's parameters tuples.
        tmp_path: the test's directory, which holds the case directory `case`.

    Returns:
        The record, `case/run_0000.prm.json`.
    """
    from ground import parameters

    case = tmp_path / "case"
    case.mkdir()
    return parameters.write(case_parameters, case / "run_0000.prm.json")


@pytest.fixture
def prm(prm_record: Path) -> str:
    """The case's `.dat`, made beside its record as the F´ host makes it.

    Args:
        prm_record: the case's record.

    Returns:
        The `.dat`'s path, as `boot` takes it.
    """
    from ground import parameters

    return str(parameters.dat(prm_record, _dictionary()))


@pytest.fixture(scope="session")
def parameter_ids() -> list[int]:
    """Every parameter's ID in the deployment's dictionary, which `boot` holds valid.

    Returns:
        The IDs, sorted.
    """
    from ground.dictionary import Dictionary

    return sorted(Dictionary(_dictionary()).parameters_by_id)


def _dictionary() -> Path:
    """The deployment's dictionary, skipping the test asking when `just fsw` has not built it.

    Returns:
        Its path.
    """
    from lab import DICTIONARY

    if not DICTIONARY.exists():
        pytest.skip("the F´ build is absent; run `just fsw`")
    return DICTIONARY
