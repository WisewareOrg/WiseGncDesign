"""The Python build's frame runner, on each configuration's GNC sub-topology with stub algorithms.

Each stub is a `Stub` named for an algorithm component the configuration instances, so the frame
runner wires it in the component's place; it logs what it is given, writes its first channel at
each step, and answers each of its instance's commands, refusing a negative first argument.
"""

import inspect
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.codegen import fpp_types
from fsw.codegen.deployment import contract_files, tick_period
from fsw.codegen.fpp_model import read
from fsw.codegen.roles import roles
from fsw.python import FrameRunner
from ground.dictionary import Dictionary, Type

LOG: list[tuple] = []
"""Each call a stub received, in order: its instance, what it was, and what it was given."""


def _value(type_: Type, number: float) -> Any:
    """A value of a dictionary type: `number` in every element, an enum's first constant, `True`.

    Args:
        type_: the type.
        number: the number.

    Returns:
        The value, as a handler or a step gets or writes it.
    """
    if type_.constants is not None:
        return sorted(type_.constants)[0]
    if type_.bools is not None:
        return True
    return np.full(type_.dtype.shape, number, type_.dtype.base.newbyteorder("=")).tolist()


class Stub:
    """An algorithm's stand-in, subclassed and named per component by `_stubs`.

    Attributes:
        component: the component's qualified name.
        instance: its instance's unqualified name.
        dictionary: the configuration's dictionary.
    """

    component: str
    instance: str
    dictionary: Dictionary

    def __init__(self, parameters: Any) -> None:
        """Logs its parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
        LOG.append((self.instance, "boot", parameters))

    def step(self, t: float, **inputs: Any) -> tuple[Any, Any]:
        """Logs the step, and writes its first channel.

        Args:
            t: s, the time.
            **inputs: each data input's value, by keyword.

        Returns:
            No output, and the first channel.
        """
        LOG.append((self.instance, "step", t, inputs))
        return fpp_types.named(f"{self.component}Outputs")(), self.written()

    def written(self) -> Any:
        """Its telemetry tuple with its first channel written, 1.5 in every element.

        Returns:
            The tuple.
        """
        telemetry = fpp_types.named(f"{self.component}Telemetry")
        channel = self.dictionary.channel(f"{self.instance}.{telemetry._fields[0]}")
        return telemetry(**{telemetry._fields[0]: _value(channel.type, 1.5)})

    @classmethod
    def command(cls, name: str, params: tuple[str, ...]) -> Any:
        """A handler of one of the instance's commands, named and parametered as the dictionary.

        Args:
            name: the command's name.
            params: its parameters' names.

        Returns:
            The handler: it logs its arguments and writes the first channel, and refuses a
            negative first argument.
        """

        def handler(self: "Stub", **args: Any) -> Any:
            """Logs the command and writes the first channel, refusing a negative first argument.

            Args:
                self: the stub.
                **args: the arguments, by name.

            Returns:
                The telemetry it writes.

            Raises:
                ValueError: the first argument is negative.
            """
            if params and np.min(args[params[0]]) < 0:
                raise ValueError(f"{name}'s {params[0]} is negative")
            LOG.append((self.instance, name, args))
            return self.written()

        keyword = inspect.Parameter.KEYWORD_ONLY
        handler.__signature__ = inspect.Signature(
            [
                inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                *(inspect.Parameter(p, keyword) for p in params),
            ]
        )
        return handler


def _stubs(configuration: str, dictionary: Dictionary) -> list[type]:
    """A `Stub` subclass per algorithm instance the configuration's dictionary holds.

    Args:
        configuration: the configuration.
        dictionary: its dictionary.

    Returns:
        The classes, each named for its component.
    """
    classes = []
    for instance in dictionary.algorithm_instances():
        short = instance.name.removeprefix(f"{configuration}.")
        commands = {
            name: Stub.command(name, tuple(p for p, _ in params))
            for name, params in dictionary.entries(short)["commands"].items()
            if dictionary.command(f"{short}.{name}").kind not in ("set", "save")
        }
        attributes = {"component": instance.component, "instance": short, "dictionary": dictionary}
        classes.append(type(instance.component.rsplit(".", 1)[-1], (Stub,), attributes | commands))
    return classes


@pytest.fixture
def case_parameters(configuration: str, algorithm_parameters: dict[str, Any]) -> tuple[Any, ...]:
    """The case's record: each algorithm instance's parameters, every element distinct.

    Args:
        configuration: the configuration.
        algorithm_parameters: each algorithm component's tuple.

    Returns:
        The configuration's instances' tuples.
    """
    instances = Dictionary.from_sub_topology(configuration).algorithm_instances()
    return tuple(algorithm_parameters[instance.component] for instance in instances)


@pytest.fixture
def runner(configuration: str, prm_record: Path) -> FrameRunner:
    """The configuration, flown with its stubs, booted, the log cleared.

    Args:
        configuration: the configuration.
        prm_record: the case's parameter record.

    Returns:
        The frame runner.
    """
    stubs = _stubs(configuration, Dictionary.from_sub_topology(configuration))
    runner = FrameRunner(configuration, prm_record, stubs)
    runner.boot()
    LOG.clear()
    return runner


def _instances(runner: FrameRunner) -> list[str]:
    """Each algorithm instance's unqualified name, in the dictionary's order.

    Args:
        runner: the frame runner.

    Returns:
        The names.
    """
    return [i.name.rsplit(".", 1)[-1] for i in runner.dictionary.algorithm_instances()]


def _first_channel(runner: FrameRunner, instance: str) -> str:
    """The first channel of an instance's telemetry tuple, which its stub writes.

    Args:
        runner: the frame runner.
        instance: the instance's unqualified name.

    Returns:
        `<instance>.<channel>`.
    """
    [held] = [i for i in runner.dictionary.algorithm_instances() if i.name.endswith(f".{instance}")]
    return f"{instance}.{fpp_types.named(f'{held.component}Telemetry')._fields[0]}"


def _command(runner: FrameRunner, instance: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """An instance's first command with a numeric first parameter, and two sets of its arguments.

    Args:
        runner: the frame runner.
        instance: the instance's unqualified name.

    Returns:
        The command's name, arguments its stub takes, and arguments its stub refuses.
    """
    for name, params in runner.dictionary.entries(instance)["commands"].items():
        command = runner.dictionary.command(f"{instance}.{name}")
        if command.kind in ("set", "save") or not params or command.types is None:
            continue
        first = command.types[0]
        if first.constants is None and first.bools is None and first.dtype.kind in "fi":
            taken = {p: _value(t, 1.0) for p, t in zip(command.params, command.types, strict=True)}
            refused = {**taken, command.params[0]: _value(command.types[0], -1.0)}
            return f"{instance}.{name}", taken, refused
    pytest.skip(f"{instance} has no command with a numeric first parameter")


def test_the_frame_runner_is_the_configuration_s_build(configuration: str, runner: FrameRunner):
    """Its period is the FPP base tick, its dictionary the sub-topology's, its build its name.

    Args:
        configuration: the configuration.
        runner: the frame runner.
    """
    assert runner.period_s == tick_period(configuration)
    assert runner.build == {"host": "fsw.python.FrameRunner"}
    generated = Dictionary.from_sub_topology(configuration)
    assert runner.dictionary.metadata == generated.metadata
    assert _instances(runner)
    for instance in _instances(runner):
        assert runner.dictionary.entries(instance) == generated.entries(instance), instance


def test_boot_builds_each_algorithm_afresh_on_its_record_parameters(
    runner: FrameRunner, algorithm_parameters: dict[str, Any]
):
    """Each boot is a power cycle: a new algorithm on the parameters the case's record holds.

    Args:
        runner: the frame runner.
        algorithm_parameters: each algorithm component's tuple, which the record holds.
    """
    runner.boot()

    booted = [(instance, rest[0]) for instance, kind, *rest in LOG if kind == "boot"]
    assert [instance for instance, _ in booted] == _instances(runner)
    for held, (_, parameters) in zip(runner.dictionary.algorithm_instances(), booted, strict=True):
        expected = algorithm_parameters[held.component]
        assert type(parameters) is type(expected)
        for name, value in expected._asdict().items():
            np.testing.assert_array_equal(getattr(parameters, name), value, err_msg=name)


def test_boot_drops_every_command_response_and_write_not_yet_drained(
    runner: FrameRunner, messages_by_role: dict[str, Any]
):
    """A power cycle keeps nothing of the last flight: no queued command, response or write.

    Args:
        runner: the frame runner.
        messages_by_role: a message for each role.
    """
    name, taken, _ = _command(runner, _instances(runner)[0])
    runner.uplink(name, taken, 7)
    runner.tick(1_000_000_000, messages_by_role)
    runner.uplink(name, taken, 8)

    runner.boot()
    runner.tick(1_000_000_000, messages_by_role)

    assert runner.responses() == []
    expected = [_first_channel(runner, instance) for instance in _instances(runner)]
    assert [name for name, _, _ in runner.telemetry()] == expected


def test_a_tick_converts_each_message_steps_at_its_time_and_commands_nothing(
    runner: FrameRunner, messages_by_role: dict[str, Any], bus_messages: dict[str, Any]
):
    """Each role's payload reaches its step as its ICD struct at `t` in s; RIO-out is empty.

    Args:
        runner: the frame runner.
        messages_by_role: a message for each role.
        bus_messages: a message of each bus struct, its members' values distinct.
    """
    commands = runner.tick(2_000_000_000, messages_by_role)

    assert commands == {}
    steps = [entry for entry in LOG if entry[1] == "step"]
    assert [instance for instance, *_ in steps] == _instances(runner)
    by_role = {role.role: role for role in roles(read(contract_files()))}
    assert set().union(*(inputs for *_, inputs in steps)) == set(messages_by_role)
    for instance, _, t, inputs in steps:
        assert t == 2.0, instance
        assert inputs, instance
        for keyword, value in inputs.items():
            role = by_role[keyword]
            assert isinstance(value, fpp_types.named(role.icd)), keyword
            payload = {m.lower(): v for m, v in bus_messages[role.bus].values.items()}
            for field in value._fields:
                np.testing.assert_array_equal(
                    getattr(value, field), payload[field.lower()], err_msg=keyword
                )
    writes = runner.telemetry()
    assert [(n, t_ns) for n, t_ns, _ in writes] == [
        (_first_channel(runner, instance), 2_000_000_000) for instance in _instances(runner)
    ]
    for name, _, raw in writes:
        expected = _value(runner.dictionary.channel(name).type, 1.5)
        assert runner.values(name, [raw]).tolist() == [expected], name
    assert runner.telemetry() == []


def test_commands_run_by_name_before_the_step_and_answer_with_f_prime_s_responses(
    runner: FrameRunner, messages_by_role: dict[str, Any]
):
    """Each command uplinked runs at the next tick, before the step, its telemetry tagged then.

    Taken, refused with its reason, a parameter's set command and an unknown name are each
    answered as F´ answers them.

    Args:
        runner: the frame runner.
        messages_by_role: a message for each role.
    """
    instance = _instances(runner)[0]
    name, taken, refused = _command(runner, instance)
    sets = [
        f"{instance}.{n}"
        for n in runner.dictionary.entries(instance)["commands"]
        if runner.dictionary.command(f"{instance}.{n}").kind == "set"
    ]
    runner.uplink(name, taken, 7)
    runner.uplink(name, refused, 8)
    if sets:
        set_type = runner.dictionary.command(sets[0]).types[0]
        runner.uplink(sets[0], {"val": _value(set_type, 1.0)}, 9)
    runner.uplink(f"{instance}.notACommand", {}, 10)
    assert runner.responses() == []

    runner.tick(1_000_000_000, messages_by_role)

    assert [(i, kind) for i, kind, *_ in LOG][:2] == [
        (instance, name.split(".")[1]),
        (instance, "step"),
    ]
    first = name.split(".")[1]
    assert runner.responses() == [
        (7, "OK", None),
        (
            8,
            "VALIDATION_ERROR",
            f"{first}'s {runner.dictionary.command(name).params[0]} is negative",
        ),
        *([(9, "INVALID_OPCODE", None)] if sets else []),
        (10, "INVALID_OPCODE", None),
    ]
    assert runner.responses() == []
    channel = _first_channel(runner, instance)
    assert [(n, t_ns) for n, t_ns, _ in runner.telemetry()][:2] == [
        (channel, 1_000_000_000),
        (channel, 1_000_000_000),
    ]


def test_a_vehicle_without_a_role_the_configuration_takes_fails_the_tick_naming_it(
    runner: FrameRunner,
):
    """A vehicle with none of the configuration's messages fails the tick, naming a role.

    Args:
        runner: the frame runner.
    """
    with pytest.raises(KeyError, match="takes the role"):
        runner.tick(1_000_000_000, {})
