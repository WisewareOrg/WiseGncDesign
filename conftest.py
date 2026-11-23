"""Fixtures every package's tests share: an F´ copy, its station, a drain, messages, parameters.

The fixtures of a configuration's F´ build range over every configuration, one per GNC
sub-topology. A test or fixture reaching the F´ build takes `fprime_configuration`, which skips a
configuration the F´ build does not build; one needing the build, or the dictionary it generates,
skips without it. Every pytest run loads this file, the judge's included, so the FPP model is
read, and the F´ build is loaded, only by the fixtures that need them.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np
import pytest

import fsw.mock
from fsw.codegen.deployment import configurations, fprime_configurations
from fsw.codegen.fpp_model import Instance
from fsw.mock import edited

if TYPE_CHECKING:
    from fsw.codegen.dictionary import Dictionary
    from fsw.codegen.fpp_model import Model
    from fsw.codegen.roles import Role
    from ground.fprime_station import FprimeStation
    from lab.fsw_extension import FswExtension


_MOCK = Path(fsw.mock.__file__).with_name("Mock.fpp")
"""The mock component's model, which includes `Extra.fppi` beside it."""

_INSTANCE = Instance("Mock.mock", "Mock.Mock", 0x1000)
"""The mock's instance."""


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
    from fsw.codegen.dictionary import Dictionary

    return Dictionary.from_component([_MOCK], _INSTANCE)


@pytest.fixture
def render_mock() -> Callable[..., Dictionary]:
    """Renders an edited mock and gives its dictionary.

    Returns:
        A function taking the directory the model and its `Extra.fppi` are written into, then
        `Mock.fpp`'s edits, `extra`, `Extra.fppi`'s edits, and `base_id`, the instance's base ID,
        each edit `(old, new)` as `fsw.mock.edited` applies it, and giving the dictionary
        `from_component` generates.
    """
    from fsw.codegen.dictionary import Dictionary

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
        (directory / "Mock.fpp").write_text(edited(_MOCK.read_text(), *edits))
        (directory / "Extra.fppi").write_text(edited(_MOCK.with_name("Extra.fppi").read_text(), *extra))
        return Dictionary.from_component([directory / "Mock.fpp"], _INSTANCE._replace(base_id=base_id))

    return render


@pytest.fixture
def fsw(fprime_configuration: str) -> FswExtension:
    """A fresh copy of the configuration's deployment, not yet booted; skips without its build.

    Args:
        fprime_configuration: the configuration.

    Returns:
        The copy.
    """
    return _copy(fprime_configuration)


@pytest.fixture
def booted(fsw: FswExtension, prm: str, parameter_ids: list[int]) -> FswExtension:
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
def station(fsw: FswExtension, dictionary: Dictionary) -> FprimeStation:
    """The ground station on the test's copy, on the dictionary the build generated.

    Args:
        fsw: the test's copy.
        dictionary: the copy's dictionary.

    Returns:
        The station.
    """
    from ground.fprime_station import FprimeStation

    return FprimeStation(fsw, dictionary)


class Booted(NamedTuple):
    """A configuration's deployment booted on parameters, and the ground station on it.

    Attributes:
        fsw: the copy, booted.
        station: the station on it, on the dictionary the build generated.
    """

    fsw: FswExtension
    station: FprimeStation


def _zero_parameters(configuration: str) -> dict[str, Any]:
    """Each algorithm instance's parameters of a configuration, every value zero, of its FPP shape.

    Args:
        configuration: the configuration.

    Returns:
        Each instance's `<Name>Parameters` tuple, by its qualified name.
    """
    from fsw.codegen.deployment import contract_model

    model = contract_model()
    return {
        instance.name: _parameters(model, instance.component, lambda count: [0.0] * count)
        for instance in _algorithm_instances(configuration)
    }


def _write_record(parameters: Mapping[str, Any], directory: Path) -> Path:
    """A case's parameter record, written as the ground writes it.

    Args:
        parameters: each instance's parameters tuple, by its qualified name.
        directory: where `run_0000.prm.json` is written.

    Returns:
        The record.
    """
    from ground import parameters as ground_parameters

    return ground_parameters.write(parameters, directory / "run_0000.prm.json")


def _dat(record: Path, configuration: str) -> str:
    """A record's `.dat`, made beside it as `lab.Adapter` makes it.

    Args:
        record: the case's record.
        configuration: the configuration, whose dictionary the `.dat` is made against.

    Returns:
        The `.dat`'s path, as `boot` takes it.
    """
    from ground import parameters as ground_parameters

    return str(ground_parameters.dat(record, _dictionary(configuration)))


def _copy(configuration: str) -> FswExtension:
    """A fresh copy of a configuration's deployment, not yet booted; skips without its build.

    Args:
        configuration: the configuration.

    Returns:
        The copy.
    """
    from lab.power_cycle import built, power_cycle

    if not built(configuration):
        pytest.skip(f"the F´ build of {configuration} is absent; run `just fsw`")
    return power_cycle(configuration)


def _parameter_ids(configuration: str) -> list[int]:
    """Every parameter's ID in a configuration's dictionary, which `boot` holds valid.

    Args:
        configuration: the configuration.

    Returns:
        The IDs, sorted.
    """
    from fsw.codegen.dictionary import Dictionary

    return sorted(Dictionary(_dictionary(configuration)).parameters_by_id)


@pytest.fixture
def boot(tmp_path_factory: pytest.TempPathFactory) -> Callable[..., Booted]:
    """Boots a configuration's deployment on the parameters a test flies; skips without its build.

    Args:
        tmp_path_factory: makes each call's case directory.

    Returns:
        A function taking the configuration and, by an algorithm instance's qualified name, the
        `<Name>Parameters` tuples to fly, every other algorithm's zero, and giving the copy booted
        on them with its station. Each call makes a copy and a case directory of its own.
    """
    from fsw.codegen.dictionary import Dictionary
    from ground.fprime_station import FprimeStation

    def boot_on(configuration: str, parameters: Mapping[str, Any] = {}) -> Booted:
        """Powers a copy on, booted on the parameters.

        Args:
            configuration: the configuration.
            parameters: tuples to fly, by the instance's qualified name.

        Returns:
            The booted copy and its station.
        """
        fsw = _copy(configuration)
        case = tmp_path_factory.mktemp("case")
        record = _write_record({**_zero_parameters(configuration), **parameters}, case)
        fsw.boot(_dat(record, configuration), _parameter_ids(configuration))
        return Booted(fsw, FprimeStation(fsw, Dictionary(_dictionary(configuration))))

    return boot_on


@pytest.fixture
def decoded() -> Callable[[Any], list[tuple[str, int, Any]]]:
    """A drain of an edge's telemetry, each downlinked value as the edge decodes it.

    Returns:
        A function taking an edge, such as an `FprimeStation` or a `FrameRunner`, and giving
        each value downlinked since the edge's last drain as `(<instance>.<channel>, time tag in
        ns, value)`, oldest first by time tag.
    """

    def drain(edge: Any) -> list[tuple[str, int, Any]]:
        """Drains the edge's telemetry, each value decoded.

        Args:
            edge: the edge.

        Returns:
            Each value's channel name, time tag in ns and value, oldest first by time tag.
        """
        flat = [
            (name, int(t_ns), value)
            for name, (times, values) in edge.decode([edge.telemetry()]).items()
            for t_ns, value in zip(times, values, strict=True)
        ]
        return sorted(flat, key=lambda write: write[1])

    return drain


@pytest.fixture
def holds() -> Callable[[Any, Mapping[str, Any]], None]:
    """An assertion that a tuple or a Basilisk payload holds values, its fields matched by name.

    Returns:
        A function taking a tuple or a payload and each field's expected values, by the field's
        name in any case. It checks every field of the first, naming the field on failure: its
        shape is the expected values', and its elements equal them.
    """

    def check(value: Any, values: Mapping[str, Any]) -> None:
        """Checks each field of the value against the expected values of its name.

        Args:
            value: a tuple, or a Basilisk payload.
            values: the expected values, by field name, ignoring case; names the value lacks are
                not read.
        """
        names = value._fields if hasattr(value, "_fields") else type(value).__dtype__.names
        expected = {name.lower(): v for name, v in values.items()}
        for name in names:
            got, want = getattr(value, name), expected[name.lower()]
            assert np.shape(got) == np.shape(want), f"{name}: shape {np.shape(got)}"
            np.testing.assert_array_equal(got, want, err_msg=name)

    return check


@pytest.fixture
def python_command() -> Callable[[Role, Any], Any]:
    """The Python build's command for an actuator role.

    Returns:
        A function taking the role and its GNC struct's value, and giving the
        `messaging.<Name>Payload` the Python build's CDH-out and RIO-out make of it.
    """
    from fsw.python.cdh import outputs
    from fsw.python.rio.messages import writer

    def command(role: Role, icd_value: Any) -> Any:
        """The role's command, as the Python build makes it.

        Args:
            role: the actuator role.
            icd_value: the value written on the role's GNC output port.

        Returns:
            The payload.
        """
        [pair] = outputs.pairings([role])
        return writer(pair.bus)(outputs.converter(pair)(icd_value))

    return command


class MockActuationCase(NamedTuple):
    """The test mock `MockActuation` configuration's actuator, its command and a case record.

    Attributes:
        configuration: the configuration, `MockActuation`.
        role: its one role, an actuator's.
        command: the payload the Python build's CDH-out and RIO-out make of the mock's command.
        record: the case's parameter record, which the F´ build boots on.
    """

    configuration: str
    role: Role
    command: Any
    record: Path


@pytest.fixture
def mock_actuation(tmp_path: Path, python_command: Callable[[Role, Any], Any]) -> MockActuationCase:
    """`MockActuation`, whose one test mock sends a fixed command each step; skips unbuilt.

    Args:
        tmp_path: where the case's record is written.
        python_command: gives the Python build's command for a role.

    Returns:
        The configuration, its role, the command and the record.
    """
    from fsw.codegen import fpp_types
    from fsw.codegen.deployment import configuration_model
    from fsw.codegen.roles import taken
    from fsw.mock import MOCK
    from fsw.mock.actuator.actuator import Actuator
    from lab import built

    configuration = "MockActuation"
    if not built(configuration):
        pytest.skip(f"the F´ build of {configuration} is absent; run `just fsw`")
    fpp_types.load(MOCK)
    [role] = taken(configuration_model(configuration, contract=MOCK), configuration)
    command = python_command(role, Actuator(None).step(0.0)[0][0])
    record = _write_record(_zero_parameters(configuration), tmp_path)
    return MockActuationCase(configuration, role, command, record)


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


def _bus_message(name: str, struct: Any, counter: Iterator[int]) -> BusMessage:
    """A message of a bus struct, each element of each member the next of 0.5, 1.5, 2.5, ...

    Args:
        name: the struct's qualified name.
        struct: the struct, as `fsw.codegen.fpp_model` reads it.
        counter: the counts, each used once.

    Returns:
        The message, its payload the `messaging.<Name>Payload` the struct mirrors.
    """
    from fsw.codegen.fields import DTYPES
    from fsw.payloads import payload_type

    payload = payload_type(name)()
    fields = {field.lower(): field for field in type(payload).__dtype__.names}
    values = {}
    for member in struct.members:
        elements = [next(counter) + 0.5 for _ in range(member.size)]
        values[member.name] = np.array(elements, DTYPES[member.type]).tolist()
        setattr(payload, fields[member.name.lower()], values[member.name])
    return BusMessage(struct, payload, values)


def _role_messages(configuration: str) -> dict[str, BusMessage]:
    """A message for each sensor role a configuration takes, every value distinct across roles.

    Two roles of one bus struct get messages of their own, so a message delivered to the wrong
    role changes the result.

    Args:
        configuration: the configuration.

    Returns:
        Each role's message, by the role's name.
    """
    from fsw.codegen.deployment import configuration_model, contract_model
    from fsw.codegen.roles import taken

    types = contract_model().types
    counter = itertools.count()
    return {
        role.role: _bus_message(role.bus, types[role.bus], counter)
        for role in taken(configuration_model(configuration), configuration)
        if role.sensor
    }


@pytest.fixture
def bus_messages() -> dict[str, BusMessage]:
    """A message of every bus struct in `lab.bus_emulator.BUS`, every value distinct.

    Each element of each member of each struct takes the next of 0.5, 1.5, 2.5, ..., in its FPP
    type, so a field or element out of place changes the result. Each struct's payload is the
    `messaging.<Name>Payload` it mirrors, as `fsw.payloads.payload_type` gives it.

    Returns:
        Each struct's message, by its qualified name.
    """
    from fsw.codegen.fpp_model import Struct, read
    from lab.bus_emulator import BUS

    counter = itertools.count()
    return {
        name: _bus_message(name, struct, counter)
        for name, struct in read([BUS]).types.items()
        if name.startswith("Bus.") and isinstance(struct, Struct)
    }


class IcdMessage(NamedTuple):
    """A GNC struct's value.

    Attributes:
        value: the struct's `fsw.codegen.fpp_types` tuple, its members' values set.
        values: each member's values by its FPP name, in the struct's order.
    """

    value: Any
    values: dict[str, Any]


@pytest.fixture
def icd_messages() -> dict[str, IcdMessage]:
    """A value of every GNC struct a role the contract declares carries, every value distinct.

    Each element of each member of each struct takes the next of 0.5, 1.5, 2.5, ..., in its FPP
    type and shape, so a field or element out of place changes the result.

    Returns:
        Each struct's value, by its qualified name.
    """
    from fsw.codegen import fpp_types
    from fsw.codegen.deployment import contract_model
    from fsw.codegen.fields import form
    from fsw.codegen.fpp_model import struct_named
    from fsw.codegen.roles import roles

    model = contract_model()
    counter = itertools.count()
    messages = {}
    for name in dict.fromkeys(role.icd for role in roles(model)):
        values = {}
        for member in struct_named(model.types, name).members:
            shape, element = form(member, model.types)
            count = int(np.prod(shape, dtype=int))
            elements = [next(counter) + 0.5 for _ in range(count)]
            values[member.name] = np.array(elements, element).reshape(shape)
        value = fpp_types.named(name)(**{m: v.copy() for m, v in values.items()})
        messages[name] = IcdMessage(value, values)
    return messages


@pytest.fixture
def bus_by_role(configuration: str) -> dict[str, tuple[int, bytes]]:
    """Each sensor role's LabBusDriver port and its message's bytes, as the emulator writes them.

    The roles are the sensor roles the configuration takes, those its GNC sub-topology exposes
    (`fsw.codegen.roles.taken`), and each port is the one its deployment wires to the role's CDH
    input, read from its FPP. Each role's message is its own, as `messages_by_role` gives it.

    Args:
        configuration: the configuration.

    Returns:
        Each role's `(port, bytes)`, by the role's name.
    """
    from fsw.codegen.deployment import bus_port, configuration_model
    from fsw.codegen.roles import taken
    from lab.bus_emulator import serialize

    messages = _role_messages(configuration)
    return {
        role.role: (bus_port(configuration, role.input), serialize(messages[role.role].payload))
        for role in taken(configuration_model(configuration), configuration)
        if role.sensor
    }


@pytest.fixture
def messages_by_role(configuration: str) -> dict[str, Any]:
    """Each sensor role's bus message as a Basilisk payload, as WiseDynamics' host gives a build.

    The roles are the sensor roles the configuration takes (`fsw.codegen.roles.taken`), each with
    a message of its own, its values distinct from every other role's.

    Args:
        configuration: the configuration.

    Returns:
        Each role's payload, by the role's name.
    """
    return {role: message.payload for role, message in _role_messages(configuration).items()}


@pytest.fixture
def bus(bus_by_role: dict[str, tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    """The bus one step takes: every sensor role's message bytes on its LabBusDriver port.

    Args:
        bus_by_role: each sensor role's port and bytes.

    Returns:
        `[(port, bytes)]`, a pair per sensor role the configuration takes.
    """
    return list(bus_by_role.values())


@pytest.fixture
def wire() -> Callable[..., Callable[..., int]]:
    """Wires a booted copy to the bus, its buffers sized to the bytes and bus structs they carry.

    Each port of a bus gets a receive buffer sized to its bytes, and each actuator role of the
    configuration a transmit buffer sized to its bus struct.

    Returns:
        A function of the copy, its configuration and a bus, `[(port, bytes)]`, giving its step:
        `step(t_ns, bus)` writes a bus of the same ports, by default the one wired, into the
        receive buffers and steps the copy, returning what the copy's `step` returns.
    """
    from fsw.codegen.deployment import bus_port, configuration_model
    from fsw.codegen.roles import taken
    from lab.bus_emulator import size

    def wire_to(fsw: FswExtension, configuration: str, bus: list[tuple[int, bytes]]) -> Callable[..., int]:
        """Makes the copy's buffers.

        Args:
            fsw: the copy, booted and not yet stepped.
            configuration: the copy's configuration.
            bus: each port and the bytes its receive buffer is sized to.

        Returns:
            The step.
        """
        buffers = {port: fsw.receive_buffer(port, len(data)) for port, data in bus}
        for role in taken(configuration_model(configuration), configuration):
            if not role.sensor:
                fsw.transmit_buffer(bus_port(configuration, role.output), size(role.bus))

        def step(t_ns: int, bus: list[tuple[int, bytes]] = bus) -> int:
            """Writes the bus into the receive buffers, then steps.

            Args:
                t_ns: ns, the step's time.
                bus: each port's bytes.

            Returns:
                The transmit buffers the step wrote, a bit per port.
            """
            for port, data in bus:
                buffers[port][:] = data
            return fsw.step(t_ns)

        return step

    return wire_to


def _algorithm_instances(configuration: str) -> tuple[Instance, ...]:
    """The GNC instances of an algorithm's component that a configuration holds.

    Args:
        configuration: the configuration.

    Returns:
        The instances, in `fsw.codegen.deployment.gnc_instances`' order.
    """
    from fsw.codegen.deployment import algorithm_components, gnc_instances

    algorithms = algorithm_components()
    return tuple(i for i in gnc_instances() if i.name.startswith(f"{configuration}.") and i.component in algorithms)


@pytest.fixture(scope="session")
def algorithm_instances() -> Callable[[str], tuple[Instance, ...]]:
    """Each configuration's GNC instances of an algorithm's component.

    Returns:
        A function taking a configuration and giving its algorithm instances, in
        `fsw.codegen.deployment.gnc_instances`' order.
    """
    return _algorithm_instances


@pytest.fixture(scope="module")
def case_parameters(fprime_configuration: str) -> dict[str, Any]:
    """Each algorithm instance's parameters in the deployment, every value zero, of its FPP shape.

    Args:
        fprime_configuration: the configuration.

    Returns:
        Each instance's `<Name>Parameters` tuple, by its qualified name.
    """
    return _zero_parameters(fprime_configuration)


def _parameters(model: Model, component: str, elements: Callable[[int], list[float]]) -> Any:
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
def algorithm_parameters() -> dict[str, Any]:
    """Each algorithm component's parameters, every element distinct, of its FPP shape and type.

    The components are `fsw.codegen.deployment.algorithm_components`. Each element of each
    parameter takes the next of 0.5, 1.5, 2.5, ..., in its FPP type, so a parameter or element out
    of place shows; a parameter that is not a number or an array of them raises `ValueError`,
    naming it.

    Returns:
        Each component's `<Name>Parameters` tuple, by its qualified name.
    """
    from fsw.codegen.deployment import algorithm_components, contract_model

    model = contract_model()
    counter = itertools.count()
    return {
        name: _parameters(model, name, lambda count: [next(counter) + 0.5 for _ in range(count)])
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
    case = tmp_path / "case"
    case.mkdir()
    return _write_record(case_parameters, case)


@pytest.fixture
def prm(prm_record: Path, fprime_configuration: str) -> str:
    """The case's `.dat`, made beside its record as `lab.Adapter` makes it.

    Args:
        prm_record: the case's record.
        fprime_configuration: the configuration, whose dictionary the `.dat` is made against.

    Returns:
        The `.dat`'s path, as `boot` takes it.
    """
    return _dat(prm_record, fprime_configuration)


@pytest.fixture(scope="module")
def parameter_ids(fprime_configuration: str) -> list[int]:
    """Every parameter's ID in the configuration's dictionary, which `boot` holds valid.

    Args:
        fprime_configuration: the configuration.

    Returns:
        The IDs, sorted.
    """
    return _parameter_ids(fprime_configuration)


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
