"""Fixtures every package's tests share: an F´ copy, its station, a drain, messages, parameters.

The fixtures of a configuration's F´ build range over every configuration, one per GNC
sub-topology. A test or fixture reaching the F´ build takes `fprime_configuration`, which skips a
configuration the F´ build does not build; one needing the build, or the dictionary it generates,
skips without it. Every pytest run loads this file, the judge's included, so the FPP model is
read, and Basilisk and F´ are imported, only by the fixtures that need them.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np
import pytest

from fsw.codegen.deployment import configurations, fprime_configurations

if TYPE_CHECKING:
    from fsw.codegen.dictionary import Dictionary
    from fsw.codegen.fpp_model import Model
    from ground.fprime_station import FprimeStation


@pytest.fixture(scope="session", params=configurations())
def configuration(request: pytest.FixtureRequest) -> str:
    """Each configuration in turn: the name of a GNC sub-topology in `fsw/fpp/gnc/`.

    Args:
        request: carries the configuration as its parameter.

    Returns:
        The configuration.
    """
    return request.param


@pytest.fixture(scope="module")
def fprime_configuration(configuration: str) -> str:
    """The configuration, for a test reaching its F´ build; skips one the F´ build does not build.

    Args:
        configuration: the configuration.

    Returns:
        The configuration, one `fsw.codegen.deployment.fprime_configurations` selects.
    """
    if configuration not in fprime_configurations():
        pytest.skip(f"the F´ build does not build {configuration}: a member has no F´ component")
    return configuration


@pytest.fixture(scope="module")
def dictionary(fprime_configuration: str) -> Dictionary:
    """The dictionary the configuration's build generated; skips the test without it.

    Args:
        fprime_configuration: the configuration.

    Returns:
        The dictionary.
    """
    from fsw.codegen.dictionary import Dictionary

    return Dictionary(_dictionary(fprime_configuration))


@pytest.fixture(scope="session")
def mock_dictionary() -> Dictionary:
    """The mock component's dictionary, instanced as `mock` at base ID 0x1000, from FPP alone.

    The component is `fsw/mock/Mock.fpp`, which includes `Extra.fppi` beside it.

    Returns:
        The dictionary.
    """
    import fsw.mock
    from fsw.codegen.dictionary import Dictionary
    from fsw.codegen.fpp_model import Instance

    return Dictionary.from_component(
        [Path(fsw.mock.__file__).with_name("Mock.fpp")], Instance("Mock.mock", "Mock.Mock", 0x1000)
    )


@pytest.fixture
def render_mock() -> Callable[..., Dictionary]:
    """Renders an edited mock and gives its dictionary.

    Returns:
        A function taking the directory the model and its `Extra.fppi` are written into, then
        `Mock.fpp`'s edits, `extra`, `Extra.fppi`'s edits, and `base_id`, the instance's base ID,
        each edit `(old, new)` as `fsw.mock.edited` applies it, and giving the dictionary
        `from_component` generates.
    """
    import fsw.mock
    from fsw.codegen.dictionary import Dictionary
    from fsw.codegen.fpp_model import Instance

    mock = Path(fsw.mock.__file__).with_name("Mock.fpp")

    def render(
        directory: Path,
        *edits: tuple[str, str],
        extra: tuple[tuple[str, str], ...] = (),
        base_id: int = 0x1000,
    ) -> Dictionary:
        """Writes the edited mock into the directory and generates its dictionary.

        Args:
            directory: where `Mock.fpp` and `Extra.fppi` are written.
            *edits: `Mock.fpp`'s edits.
            extra: `Extra.fppi`'s edits.
            base_id: the instance's base ID.

        Returns:
            The dictionary.
        """
        (directory / "Mock.fpp").write_text(fsw.mock.edited(mock.read_text(), *edits))
        (directory / "Extra.fppi").write_text(
            fsw.mock.edited(mock.with_name("Extra.fppi").read_text(), *extra)
        )
        return Dictionary.from_component(
            [directory / "Mock.fpp"], Instance("Mock.mock", "Mock.Mock", base_id)
        )

    return render


@pytest.fixture
def fsw(fprime_configuration: str) -> ModuleType:
    """A fresh copy of the configuration's deployment, not yet booted; skips without its build.

    Args:
        fprime_configuration: the configuration.

    Returns:
        The copy.
    """
    from lab.power_cycle import built, power_cycle

    if not built(fprime_configuration):
        pytest.skip(f"the F´ build of {fprime_configuration} is absent; run `just fsw`")

    return power_cycle(fprime_configuration)


@pytest.fixture
def booted(fsw: ModuleType, prm: str, parameter_ids: list[int]) -> ModuleType:
    """The test's copy of the deployment, booted idle on the case's parameters.

    Args:
        fsw: the test's copy.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.

    Returns:
        The copy, `fsw` itself.
    """
    fsw.boot(prm, parameter_ids)
    return fsw


@pytest.fixture
def station(fsw: ModuleType, dictionary: Dictionary) -> FprimeStation:
    """The ground station on the test's copy, on the dictionary the build generated.

    Args:
        fsw: the test's copy.
        dictionary: the copy's dictionary.

    Returns:
        The station.
    """
    from ground.fprime_station import FprimeStation

    return FprimeStation(fsw, dictionary)


@pytest.fixture
def decoded() -> Callable[[Any], list[tuple[str, int, Any]]]:
    """A drain of an edge's telemetry, each write decoded to its value by the edge.

    Returns:
        A function taking an edge, such as an `FprimeStation` or a `FrameRunner`, and giving
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


@pytest.fixture(scope="session")
def contract_model() -> Model:
    """The repository's contract's model, read once per session.

    Returns:
        The model `fsw.codegen.fpp_model.read` gives of `fsw.codegen.deployment.contract_files`.
    """
    from fsw.codegen.deployment import contract_files
    from fsw.codegen.fpp_model import read

    return read(contract_files())


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


class IcdMessage(NamedTuple):
    """A GNC struct's value.

    Attributes:
        value: the struct's `fsw.codegen.fpp_types` tuple, its members' values set.
        values: each member's values by its FPP name, in the struct's order.
    """

    value: Any
    values: dict[str, Any]


@pytest.fixture
def icd_messages(contract_model: Model) -> dict[str, IcdMessage]:
    """A value of every GNC struct a role the contract declares carries, every value distinct.

    Each element of each member of each struct takes the next of 0.5, 1.5, 2.5, ..., in its FPP
    type and shape, so a field or element out of place changes the result.

    Args:
        contract_model: the contract's model, which declares the roles and shapes the structs.

    Returns:
        Each struct's value, by its qualified name.
    """
    from fsw.codegen import fpp_types
    from fsw.codegen.deployment import CONTRACT
    from fsw.codegen.fields import form
    from fsw.codegen.roles import roles

    fpp_types.load(CONTRACT)
    counter = itertools.count()
    messages = {}
    for name in dict.fromkeys(role.icd for role in roles(contract_model)):
        values = {}
        for member in contract_model.types[name].members:
            shape, element = form(member, contract_model.types)
            count = int(np.prod(shape, dtype=int))
            elements = [next(counter) + 0.5 for _ in range(count)]
            values[member.name] = np.array(elements, element).reshape(shape)
        value = fpp_types.named(name)(**{m: v.copy() for m, v in values.items()})
        messages[name] = IcdMessage(value, values)
    return messages


@pytest.fixture
def bus_by_role(
    configuration: str, bus_messages: dict[str, BusMessage]
) -> dict[str, tuple[int, bytes]]:
    """Each sensor role's LabBusDriver port and its message's bytes, as the emulator writes them.

    The roles are the sensor roles the configuration takes, those its GNC sub-topology exposes
    (`fsw.codegen.roles.taken`), and each port is the one its deployment wires to the role's CDH
    input, read from its FPP.

    Args:
        configuration: the configuration.
        bus_messages: a message of each bus struct.

    Returns:
        Each role's `(port, bytes)`, by the role's name.
    """
    from fsw.codegen.deployment import bus_port, configuration_model
    from fsw.codegen.roles import taken
    from lab.bus_emulator import serialize

    return {
        role.role: (
            bus_port(configuration, role.input),
            serialize(bus_messages[role.bus].payload),
        )
        for role in taken(configuration_model(configuration), configuration)
        if role.sensor
    }


@pytest.fixture
def messages_by_role(configuration: str, bus_messages: dict[str, BusMessage]) -> dict[str, Any]:
    """Each sensor role's bus message as a Basilisk payload, as WiseDynamics' host gives a build.

    The roles are the sensor roles the configuration takes (`fsw.codegen.roles.taken`), each with
    its bus struct's message.

    Args:
        configuration: the configuration.
        bus_messages: a message of each bus struct.

    Returns:
        Each role's payload, by the role's name.
    """
    from fsw.codegen.deployment import configuration_model
    from fsw.codegen.roles import taken

    return {
        role.role: bus_messages[role.bus].payload
        for role in taken(configuration_model(configuration), configuration)
        if role.sensor
    }


@pytest.fixture
def bus(bus_by_role: dict[str, tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    """The bus one step takes: every sensor role's message bytes on its LabBusDriver port.

    Args:
        bus_by_role: each sensor role's port and bytes.

    Returns:
        `[(port, bytes)]`, a pair per sensor role the configuration takes.
    """
    return list(bus_by_role.values())


@pytest.fixture(scope="module")
def case_parameters(dictionary: Dictionary, contract_model: Model) -> dict[str, Any]:
    """Each algorithm instance's parameters in the deployment, every value zero, of its FPP shape.

    The instances are those the deployment's dictionary holds, so the case skips without it. A
    test module flying an algorithm's own values overrides this fixture, swapping that algorithm's
    tuple in.

    Args:
        dictionary: the configuration's dictionary, which names the instances.
        contract_model: the contract's model, which shapes the parameters.

    Returns:
        Each instance's `<Name>Parameters` tuple, by its qualified name.
    """
    return {
        instance.name: _parameters(contract_model, instance.component, lambda count: [0.0] * count)
        for instance in dictionary.algorithm_instances()
    }


def _parameters(model: Any, component: str, elements: Callable[[int], list[float]]) -> Any:
    """A component's parameters tuple, each parameter of its FPP shape and type.

    Args:
        model: the contract's model.
        component: the component's qualified name.
        elements: gives a parameter's elements, flattened, from how many it has.

    Returns:
        The component's `<Name>Parameters` tuple.

    Raises:
        ValueError: a parameter is not a number or an array of them, naming it.
    """
    from fsw.codegen import fpp_types
    from fsw.codegen.fields import form
    from fsw.codegen.fpp_model import Member

    values = {}
    for parameter in model.components[component].parameters:
        shape, element = form(Member(parameter.name, parameter.type, None), model.types)
        if not isinstance(element, np.dtype):
            raise ValueError(f"{component}.{parameter.name} is {element}, not a number")
        count = int(np.prod(shape, dtype=int))
        values[parameter.name] = np.array(elements(count), element).reshape(shape).tolist()
    return fpp_types.parameters_from(fpp_types.named(f"{component}Parameters"), values)


@pytest.fixture(scope="module")
def rate_groups(configuration: str) -> list[str]:
    """The configuration's rate groups, its GNC sub-topology's `Svc.PassiveRateGroup` instances.

    Args:
        configuration: the configuration.

    Returns:
        Their unqualified names, sorted.
    """
    from fsw.codegen.deployment import configuration_model

    instances = configuration_model(configuration).instances
    return sorted(
        name.rsplit(".", 1)[-1]
        for name, instance in instances.items()
        if name.startswith(f"{configuration}.") and instance.component == "Svc.PassiveRateGroup"
    )


@pytest.fixture
def algorithm_parameters(contract_model: Model) -> dict[str, Any]:
    """Each algorithm component's parameters, every element distinct, of its FPP shape and type.

    The components are `fsw.codegen.deployment.algorithm_components`. Each element of each
    parameter takes the next of 0.5, 1.5, 2.5, ..., in its FPP type, so a parameter or element out
    of place shows; a parameter that is not a number or an array of them raises `ValueError`,
    naming it.

    Args:
        contract_model: the contract's model, which shapes the parameters.

    Returns:
        Each component's `<Name>Parameters` tuple, by its qualified name.
    """
    from fsw.codegen.deployment import algorithm_components

    counter = itertools.count()
    return {
        name: _parameters(
            contract_model, name, lambda count: [next(counter) + 0.5 for _ in range(count)]
        )
        for name in sorted(algorithm_components())
    }


@pytest.fixture
def prm_record(case_parameters: dict[str, Any], tmp_path: Path) -> Path:
    """A case's parameter record, written as the ground writes it, in a case directory of its own.

    Args:
        case_parameters: each instance's parameters tuple, by its qualified name.
        tmp_path: the test's directory, which holds the case directory `case`.

    Returns:
        The record, `case/run_0000.prm.json`.
    """
    from ground import parameters

    case = tmp_path / "case"
    case.mkdir()
    return parameters.write(case_parameters, case / "run_0000.prm.json")


@pytest.fixture
def prm(prm_record: Path, fprime_configuration: str) -> str:
    """The case's `.dat`, made beside its record as `lab.Adapter` makes it.

    Args:
        prm_record: the case's record.
        fprime_configuration: the configuration, whose dictionary the `.dat` is made against.

    Returns:
        The `.dat`'s path, as `boot` takes it.
    """
    from ground import parameters

    return str(parameters.dat(prm_record, _dictionary(fprime_configuration)))


@pytest.fixture(scope="module")
def parameter_ids(dictionary: Dictionary) -> list[int]:
    """Every parameter's ID in the configuration's dictionary, which `boot` holds valid.

    Args:
        dictionary: the configuration's dictionary.

    Returns:
        The IDs, sorted.
    """
    return sorted(dictionary.parameters_by_id)


def _dictionary(configuration: str) -> Path:
    """A configuration's dictionary, skipping the test asking when `just fsw` has not built it.

    Args:
        configuration: the configuration.

    Returns:
        Its path.
    """
    from lab import dictionary_path

    path = dictionary_path(configuration)
    if not path.exists():
        pytest.skip(f"the F´ build of {configuration} is absent; run `just fsw`")
    return path
