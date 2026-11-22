"""The FPP file lists, and each configuration's deployment, its role wiring generated from FPP.

A deployment's file list is the contract's, its GNC sub-topology and its rendered topology. The
role wiring is checked on mock configurations rendered from the contract's roles, read through
FPP's own analysis; which configurations the F´ build builds, on a mock contract.
"""

import os
from pathlib import Path

import pytest

from fsw.codegen.deployment import (
    CONTRACT,
    REPOSITORY,
    Contract,
    algorithm_files,
    bus_port,
    configuration_model,
    configurations,
    contract_files,
    contract_model,
    fpp_files,
    fprime_configurations,
    gnc_instances,
    main,
    render,
    tick_period,
)
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.roles import Role, roles
from fsw.mock import MOCK, device, device_contract, edited, exposure, port, sub_topology

DECLARED = roles(contract_model())
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
        REPOSITORY / "fsw" / "fpp" / "gnc" / f"{configuration}.fpp",
        tmp_path / f"{configuration}Fsw.fpp",
    )


def test_every_gnc_instance_is_in_a_configuration():
    """Each GNC instance is qualified by a configuration, and each configuration has instances."""
    assert {instance.name.split(".")[0] for instance in gnc_instances()} == set(configurations())


def test_a_configuration_s_base_tick_period_is_its_fpp_constant():
    """`tickPeriod`, in s, is a constant of the configuration's sub-topology."""
    assert tick_period("MockFrame", contract=MOCK) == 0.5
    assert "MockFrame.Gnc" in configuration_model("MockFrame", contract=MOCK).topologies


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
    contract = device_contract(tmp_path, name, DECLARED, [exposure(r) for r in exposed])
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
            assert bus_port(name, port(role), contract=contract) == k, role.role


def test_a_render_leaves_a_topology_whose_text_is_unchanged_untouched(
    configuration: str, tmp_path: Path
):
    """A second render keeps the file, so the F´ build does not autocode it again; a stale one goes.

    Args:
        configuration: the configuration.
        tmp_path: where the topology is rendered.
    """
    topology = render(configuration, tmp_path)
    os.utime(topology, ns=(0, 0))

    assert render(configuration, tmp_path) == topology
    assert topology.stat().st_mtime_ns == 0

    text = topology.read_text()
    topology.write_text(text + "\n")
    render(configuration, tmp_path)
    assert topology.read_text() == text


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
    contract = device_contract(tmp_path, name, DECLARED, [exposure(r) for r in SENSORS])
    role = SENSORS[0]
    other = len(SENSORS)
    original = (REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in").read_text()
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

    The configuration's two members' components are defined in two directories; it is built only
    once both hold a `CMakeLists.txt`.

    Args:
        tmp_path: where the mock is written.
    """
    (tmp_path / "gnc").mkdir()
    fpps = []
    for name in ("First", "Second"):
        (tmp_path / name).mkdir()
        fpps.append(tmp_path / name / f"{name}.fpp")
        fpps[-1].write_text(device(name, []))
    (tmp_path / "gnc" / "Gated.fpp").write_text(
        sub_topology("Gated", [("first", "MockGnc.First"), ("second", "MockGnc.Second")])
    )
    contract = Contract(tuple(fpps), tmp_path / "gnc")
    assert fprime_configurations(contract=contract) == ()

    (tmp_path / "First" / "CMakeLists.txt").touch()
    assert fprime_configurations(contract=contract) == ()

    (tmp_path / "Second" / "CMakeLists.txt").touch()
    assert fprime_configurations(contract=contract) == ("Gated",)


def test_every_algorithm_s_fpp_is_in_the_contract_with_or_without_an_f_prime_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """An algorithm is found by its `.fpp` alone, so a Python-only algorithm is in the contract.

    Args:
        tmp_path: the repository the algorithms are read from.
        monkeypatch: points `fsw.codegen.deployment` at it.
    """
    for name, fprime in (("built", True), ("python_only", False)):
        (tmp_path / "algorithms" / name).mkdir(parents=True)
        (tmp_path / "algorithms" / name / f"{name}.fpp").touch()
        if fprime:
            (tmp_path / "algorithms" / name / "CMakeLists.txt").touch()
    monkeypatch.setattr("fsw.codegen.deployment.REPOSITORY", tmp_path)

    assert algorithm_files() == (
        tmp_path / "algorithms" / "built" / "built.fpp",
        tmp_path / "algorithms" / "python_only" / "python_only.fpp",
    )


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
