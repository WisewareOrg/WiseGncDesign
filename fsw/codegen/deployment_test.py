"""The FPP file lists, and each configuration's deployment, its role wiring generated from FPP.

A deployment's file list is the contract's, its GNC sub-topology and its rendered topology. The
role wiring is checked on mock configurations rendered from the contract's roles, read through
FPP's own analysis; which configurations the F´ build builds, on a mock contract.
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from fsw.codegen.deployment import (
    CONTRACT,
    Contract,
    algorithm_components,
    algorithm_files,
    bus_port,
    configuration_model,
    configurations,
    contract_files,
    fpp_files,
    fprime_configurations,
    gnc_instances,
    main,
    tick_period,
)
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.roles import Role, roles, taken
from fsw.mock import MOCK, device, edited, sub_topology

_REPOSITORY = Path(__file__).resolve().parents[2]

DECLARED = roles(read(contract_files()))
"""Every role the contract declares."""

SENSORS = [role for role in DECLARED if role.sensor]
"""Every sensor role."""

ACTUATORS = [role for role in DECLARED if not role.sensor]
"""Every actuator role."""


def test_a_deployment_s_files_are_the_contract_s_then_its_gnc_and_topology(
    configuration: str, tmp_path: Path
):
    """`fpp_files` extends `contract_files`, so both builds read one list.

    Args:
        configuration: the configuration.
        tmp_path: where the deployment's topology is rendered.
    """
    files = fpp_files(configuration, tmp_path)

    assert files == (
        *contract_files(),
        _REPOSITORY / "fsw" / "fpp" / "gnc" / f"{configuration}.fpp",
        tmp_path / f"{configuration}Fsw.fpp",
    )
    text = (tmp_path / f"{configuration}Fsw.fpp").read_text()
    assert "@CONFIGURATION@" not in text
    assert "@SIMULATION@" not in text


def test_the_contract_holds_the_bus_structs_and_every_algorithm_s_files():
    """The bus structs and the algorithms the F´ build takes are in the contract."""
    files = contract_files()

    assert _REPOSITORY / "fsw" / "fpp" / "interfaces" / "Bus.fpp" in files
    assert algorithm_files()
    assert set(algorithm_files()) <= set(files)


def test_the_algorithm_components_are_those_an_algorithm_s_fpp_defines():
    """Each is defined in an algorithm's file; a GNC instance's component is one, or is F´'s."""
    found = algorithm_components()
    components = read(contract_files()).components

    assert found
    for name in found:
        assert components[name].file in algorithm_files(), name
    for instance in gnc_instances():
        in_algorithm = components[instance.component].file in algorithm_files()
        assert (instance.component in found) == in_algorithm, instance.name
    assert "Svc.PassiveRateGroup" not in found


def test_the_configurations_are_the_gnc_sub_topologies_sorted_by_name():
    """Each configuration has its sub-topology's file, and qualifies every GNC instance."""
    found = configurations()

    assert found
    assert list(found) == sorted(found)
    for configuration in found:
        assert (_REPOSITORY / "fsw" / "fpp" / "gnc" / f"{configuration}.fpp").is_file()
    assert {instance.name.split(".")[0] for instance in gnc_instances()} == set(found)


def test_a_configuration_s_base_tick_period_is_its_fpp_constant():
    """`tickPeriod`, in s, beside the sub-topology's dividers, read from its model once."""
    assert tick_period("MockFrame", contract=MOCK) == 0.5
    model = configuration_model("MockFrame", contract=MOCK)
    assert configuration_model("MockFrame", contract=MOCK) is model
    assert "MockFrame.Gnc" in model.topologies


def test_a_configuration_without_a_tick_period_is_refused_naming_the_constant(
    monkeypatch: pytest.MonkeyPatch,
):
    """A sub-topology that declares no `tickPeriod` raises, naming the constant it lacks.

    Args:
        monkeypatch: gives the configuration a model without the constant.
    """
    model = configuration_model("MockFrame", contract=MOCK)
    constants = {k: v for k, v in model.constants.items() if k != "MockFrame.tickPeriod"}
    monkeypatch.setattr(
        "fsw.codegen.deployment.configuration_model",
        lambda _, **__: model._replace(constants=constants),
    )

    with pytest.raises(KeyError, match=r"MockFrame\.tickPeriod"):
        tick_period("MockFrame", contract=MOCK)


def _mock(directory: Path, name: str, exposed: Sequence[Role]) -> Contract:
    """A mock contract of one configuration, whose device takes every declared role.

    Args:
        directory: where the device and the configuration are written.
        name: the configuration.
        exposed: the roles its sub-topology exposes.

    Returns:
        The contract.
    """
    (directory / "gnc").mkdir()
    fpp = directory / "Device.fpp"
    fpp.write_text(device("Device", DECLARED))
    ports = [role.input if role.sensor else role.output for role in exposed]
    (directory / "gnc" / f"{name}.fpp").write_text(
        sub_topology(
            name, [("device", "MockGnc.Device")], [f"port {p} = device.{p}" for p in ports]
        )
    )
    return Contract((fpp,), directory / "gnc")


def _simulation(model: Model, name: str) -> set[tuple[str, str, int, str, str, int]]:
    """A rendered deployment's connections to and from LabBusDriver and the CDH.

    Args:
        model: the deployment's model.
        name: the configuration.

    Returns:
        Each connection, as its ends with the deployment's module dropped from each instance.
    """
    simulation = {"WiseFsw.labBusDriver", "WiseFsw.cdh"}
    return {
        (
            c.from_instance.removeprefix("WiseFsw."),
            c.from_port,
            c.from_index,
            c.to_instance.removeprefix("WiseFsw."),
            c.to_port,
            c.to_index,
        )
        for c in model.topologies[f"WiseFsw.{name}Fsw"]
        if {c.from_instance, c.to_instance} & simulation
    }


@pytest.mark.parametrize(
    "exposed",
    [DECLARED, SENSORS, ACTUATORS, []],
    ids=["every-role", "sensors-only", "actuators-only", "no-role"],
)
def test_a_configuration_s_role_wiring_is_generated_from_the_roles_it_takes(
    tmp_path: Path, exposed: list[Role]
):
    """The k-th sensor is fed from `busOut[k]`, the k-th actuator feeds `busIn[k]`, through cdh.

    FPP's own analysis accepts each rendered deployment, so each end is type-checked; a
    configuration taking no role renders an empty Simulation group.

    Args:
        tmp_path: where the mock and its deployment are rendered.
        exposed: the roles the mock's sub-topology exposes.
    """
    assert SENSORS and ACTUATORS
    name = "Wired"
    contract = _mock(tmp_path, name, exposed)
    gnc = f"{name}.device"

    model = read(fpp_files(name, tmp_path, contract=contract))

    sensors = [role for role in exposed if role.sensor]
    actuators = [role for role in exposed if not role.sensor]
    wired = {
        connection
        for k, role in enumerate(sensors)
        for connection in (
            ("labBusDriver", "busOut", k, "cdh", role.input, 0),
            ("cdh", role.output, 0, gnc, role.input, 0),
        )
    } | {
        connection
        for k, role in enumerate(actuators)
        for connection in (
            (gnc, role.output, 0, "cdh", role.input, 0),
            ("cdh", role.output, 0, "labBusDriver", "busIn", k),
        )
    }
    assert _simulation(model, name) == wired
    text = (tmp_path / f"{name}Fsw.fpp").read_text()
    assert "@" not in text.replace("@ ", "")
    for of in (sensors, actuators):
        for k, role in enumerate(of):
            port = role.input if role.sensor else role.output
            assert bus_port(name, port, contract=contract) == k, role.role


def test_the_repository_s_configurations_wire_their_roles_through_the_shared_template(
    configuration: str,
):
    """Each taken role's LabBusDriver index is its place among the roles of its direction.

    Args:
        configuration: the configuration.
    """
    found = taken(configuration_model(configuration), configuration)
    for direction in (True, False):
        of = [role for role in found if role.sensor == direction]
        for k, role in enumerate(of):
            port = role.input if role.sensor else role.output
            assert bus_port(configuration, port) == k, role.role


def test_a_cdh_port_no_lab_bus_driver_port_feeds_is_refused_naming_it(configuration: str):
    """A port the deployment leaves off LabBusDriver raises, naming it and the configuration.

    Args:
        configuration: the configuration.
    """
    with pytest.raises(
        ValueError, match=rf"{configuration}.*cdh\.notARoleIn.*LabBusDriver port\(s\) \[\]"
    ):
        bus_port(configuration, "notARoleIn")


def test_a_cdh_port_two_lab_bus_driver_ports_feed_is_refused_naming_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A template that wires a second LabBusDriver port to a role's input raises, naming both.

    Args:
        tmp_path: where the mock, its deployment and the twice-wired template are written.
        monkeypatch: renders the deployment from that template.
    """
    name = "Twice"
    contract = _mock(tmp_path, name, SENSORS)
    role = SENSORS[0]
    other = len(SENSORS)
    original = (_REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in").read_text()
    template = tmp_path / "Fsw.fpp.in"
    template.write_text(
        edited(
            original,
            (
                "@SIMULATION@\n",
                f"@SIMULATION@\n      labBusDriver.busOut[{other}] -> cdh.{role.input}\n",
            ),
        )
    )
    monkeypatch.setattr("fsw.codegen.deployment._TEMPLATE", template)

    with pytest.raises(
        ValueError, match=rf"cdh\.{role.input} to LabBusDriver port\(s\) \[0, {other}\], not one"
    ):
        bus_port(name, role.input, contract=contract)


def test_the_f_prime_build_builds_a_configuration_only_when_each_member_has_an_f_prime_component(
    tmp_path: Path,
):
    """A member whose component's `.fpp` has no `CMakeLists.txt` beside it keeps it out of F´.

    Args:
        tmp_path: where the mock is written.
    """
    contract = _mock(tmp_path, "Gated", DECLARED)
    assert fprime_configurations(contract=contract) == ()

    (tmp_path / "CMakeLists.txt").touch()

    assert fprime_configurations(contract=contract) == ("Gated",)
    assert fprime_configurations() == configurations()


def test_the_renderer_renders_and_names_every_f_prime_configuration_of_both_contracts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """`python -m fsw.codegen.deployment <dir>` prints a line per configuration it renders, alone.

    Each line is the configuration, a tab, and its GNC sub-topology's path; the repository's
    contract's and the test mocks' F´ configurations are each rendered into `<dir>/<name>/`.

    Args:
        tmp_path: the directory.
        capsys: reads what the renderer prints.
    """
    main([str(tmp_path)])

    expected = [
        f"{name}\t{contract.gnc / f'{name}.fpp'}"
        for contract in (CONTRACT, MOCK)
        for name in fprime_configurations(contract=contract)
    ]
    assert expected
    assert capsys.readouterr().out.splitlines() == expected
    for line in expected:
        name = line.split("\t")[0]
        assert (tmp_path / name / f"{name}Fsw.fpp").is_file(), name
