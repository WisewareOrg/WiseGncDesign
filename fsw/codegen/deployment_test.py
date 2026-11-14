"""The FPP file lists: a deployment's is the contract's, its GNC sub-topology and its topology."""

from pathlib import Path

import pytest

from fsw.codegen.deployment import algorithm_files, contract_files, fpp_files, gnc_instance
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
    monkeypatch.setattr("fsw.codegen.deployment._gnc_instances", lambda: twice)

    with pytest.raises(
        ValueError,
        match=r"instanced 2 times in fsw/fpp/gnc: \['ImuDeadReckoning\.nav', 'Other\.nav'\]",
    ):
        gnc_instance("Gnc.ImuDeadReckoner")
