"""The FPP file lists: a deployment's is the contract's, its GNC sub-topology and its topology."""

from pathlib import Path

import pytest

from fsw.codegen.deployment import (
    algorithm_components,
    algorithm_files,
    bus_port,
    configuration_model,
    configurations,
    contract_files,
    fpp_files,
    gnc_instances,
    tick_period,
)
from fsw.codegen.fpp_model import Model, read
from fsw.codegen.roles import roles
from fsw.mock import MOCK

_REPOSITORY = Path(__file__).resolve().parents[2]


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


def test_a_cdh_port_s_bus_port_is_the_lab_bus_driver_port_the_deployment_wires_to_it(
    configuration: str, contract_model: Model
):
    """Each role's `cdh.<role>In` is fed by the `labBusDriver.busOut` index the template wires.

    Args:
        configuration: the configuration.
        contract_model: the contract's model, which declares the roles.
    """
    declared = roles(contract_model)
    template = (_REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in").read_text()
    assert declared

    for role in declared:
        port = bus_port(configuration, role.input)
        assert f"labBusDriver.busOut[{port}] -> cdh.{role.input}" in template, role.role


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
    configuration: str,
    contract_model: Model,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A template that wires a second LabBusDriver port to a role's input raises, naming both.

    The second port is the lowest that no role's input takes.

    Args:
        configuration: the configuration.
        contract_model: the contract's model, which declares the roles.
        tmp_path: where the twice-wired template is written.
        monkeypatch: renders the deployment from that template.
    """
    declared = roles(contract_model)
    role = declared[0]
    port = bus_port(configuration, role.input)
    taken = {bus_port(configuration, r.input) for r in declared}
    [bus_out] = [
        p for p in contract_model.components["Bus.LabBusDriver"].outputs if p.name == "busOut"
    ]
    free = [i for i in range(bus_out.size) if i not in taken]
    assert free, "every LabBusDriver port is taken"
    other = free[0]
    wired = f"labBusDriver.busOut[{port}] -> cdh.{role.input}"
    original = (_REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in").read_text()
    assert wired in original
    template = tmp_path / "Fsw.fpp.in"
    template.write_text(
        original.replace(wired, f"{wired}\n      labBusDriver.busOut[{other}] -> cdh.{role.input}")
    )
    monkeypatch.setattr("fsw.codegen.deployment._TEMPLATE", template)
    bus_port.cache_clear()
    try:
        found = ", ".join(map(str, sorted((port, other))))
        with pytest.raises(
            ValueError, match=rf"cdh\.{role.input} to LabBusDriver port\(s\) \[{found}\], not one"
        ):
            bus_port(configuration, role.input)
    finally:
        bus_port.cache_clear()
