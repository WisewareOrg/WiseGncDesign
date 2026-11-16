"""The FPP file lists: a deployment's is the contract's, its GNC sub-topology and its topology."""

from pathlib import Path

import pytest

from fsw.codegen.deployment import (
    algorithm_files,
    bus_port,
    configuration_model,
    contract_files,
    fpp_files,
    gnc_instance,
    tick_period,
)
from fsw.codegen.fpp_model import Instance

_REPOSITORY = Path(__file__).resolve().parents[2]


def test_a_deployment_s_files_are_the_contract_s_then_its_gnc_and_topology(tmp_path: Path):
    """`fpp_files` extends `contract_files`, so both builds read one list.

    Args:
        tmp_path: where the deployment's topology is rendered.
    """
    files = fpp_files("ImuDeadReckoning", tmp_path)

    assert files == (
        *contract_files(),
        _REPOSITORY / "fsw" / "fpp" / "gnc" / "ImuDeadReckoning.fpp",
        tmp_path / "ImuDeadReckoningFsw.fpp",
    )


def test_the_contract_holds_the_bus_structs_and_every_algorithm_s_files():
    """The bus structs and the algorithms the F´ build takes are in the contract."""
    files = contract_files()

    assert _REPOSITORY / "fsw" / "fpp" / "interfaces" / "Bus.fpp" in files
    reckoner = _REPOSITORY / "algorithms" / "imu_dead_reckoning" / "ImuDeadReckoner.fpp"
    assert reckoner in algorithm_files()
    assert set(algorithm_files()) <= set(files)


def test_a_component_s_gnc_instance_is_its_one_instance_in_the_gnc_sub_topologies():
    """Nav is found qualified by its sub-topology; a deployment's own instance is in none."""
    assert gnc_instance("Gnc.ImuDeadReckoner") == Instance(
        "ImuDeadReckoning.nav", "Gnc.ImuDeadReckoner", 0x1000
    )
    with pytest.raises(ValueError, match=r"Svc\.PrmDb is instanced 0 times in fsw/fpp/gnc"):
        gnc_instance("Svc.PrmDb")


def test_a_component_instanced_twice_is_refused_naming_both_instances(
    monkeypatch: pytest.MonkeyPatch,
):
    """Two GNC instances of one component leave no one key; both are named.

    Args:
        monkeypatch: gives the lookup a second instance of nav's component.
    """
    nav = gnc_instance("Gnc.ImuDeadReckoner")
    twice = (nav, nav._replace(name="Other.nav", base_id=0x2000))
    monkeypatch.setattr("fsw.codegen.deployment.gnc_instances", lambda: twice)

    with pytest.raises(
        ValueError,
        match=r"instanced 2 times in fsw/fpp/gnc: \['ImuDeadReckoning\.nav', 'Other\.nav'\]",
    ):
        gnc_instance("Gnc.ImuDeadReckoner")


def test_a_configuration_s_base_tick_period_is_its_fpp_constant():
    """`tickPeriod`, in s, beside the sub-topology's dividers, read from its model once."""
    assert tick_period("ImuDeadReckoning") == 1.0
    assert configuration_model("ImuDeadReckoning") is configuration_model("ImuDeadReckoning")
    assert "ImuDeadReckoning.Gnc" in configuration_model("ImuDeadReckoning").topologies


def test_a_configuration_without_a_tick_period_is_refused_naming_the_constant(
    monkeypatch: pytest.MonkeyPatch,
):
    """A sub-topology that declares no `tickPeriod` raises, naming the constant it lacks.

    Args:
        monkeypatch: gives the configuration a model without the constant.
    """
    model = configuration_model("ImuDeadReckoning")
    constants = {k: v for k, v in model.constants.items() if k != "ImuDeadReckoning.tickPeriod"}
    monkeypatch.setattr(
        "fsw.codegen.deployment.configuration_model", lambda _: model._replace(constants=constants)
    )

    with pytest.raises(KeyError, match=r"ImuDeadReckoning\.tickPeriod"):
        tick_period("ImuDeadReckoning")


def test_a_cdh_port_s_bus_port_is_the_simhub_port_the_deployment_wires_to_it():
    """The IMU's `cdh.imuIn` is fed by `simHub.busOut[0]`, as the rendered topology wires it."""
    assert bus_port("ImuDeadReckoning", "imuIn") == 0


def test_a_cdh_port_no_simhub_port_feeds_is_refused_naming_it():
    """A port the deployment does not wire to SimHub raises, naming it and the configuration."""
    with pytest.raises(ValueError, match=r"ImuDeadReckoning.*cdh\.starIn.*SimHub port\(s\) \[\]"):
        bus_port("ImuDeadReckoning", "starIn")


def test_a_cdh_port_two_simhub_ports_feed_is_refused_naming_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A template that wires a second SimHub port to `cdh.imuIn` raises, naming both ports.

    Args:
        tmp_path: where the twice-wired template is written.
        monkeypatch: renders the deployment from that template.
    """
    template = tmp_path / "Fsw.fpp.in"
    wired = "simHub.busOut[0] -> cdh.imuIn"
    original = (_REPOSITORY / "fsw" / "fprime" / "deployment" / "Fsw.fpp.in").read_text()
    assert wired in original
    template.write_text(original.replace(wired, f"{wired}\n      simHub.busOut[1] -> cdh.imuIn"))
    monkeypatch.setattr("fsw.codegen.deployment._TEMPLATE", template)
    bus_port.cache_clear()
    try:
        with pytest.raises(ValueError, match=r"cdh\.imuIn to SimHub port\(s\) \[0, 1\], not one"):
            bus_port("ImuDeadReckoning", "imuIn")
    finally:
        bus_port.cache_clear()
