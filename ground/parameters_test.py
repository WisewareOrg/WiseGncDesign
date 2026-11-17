"""The ground's parameter record of a case, and the `.dat` F´'s own tool makes from it.

The parameters are every algorithm component's, generated from the contract, and the `.dat` is
made against each configuration's dictionary.
"""

import json
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.codegen.deployment import gnc_instance, gnc_instances
from fsw.codegen.fpp_model import Instance
from ground import parameters
from ground.dictionary import Dictionary
from lab import dictionary_path

STRAY = namedtuple("StrayParameters", ["gain"])
"""A toy component's parameters tuple, of a component no GNC sub-topology instances."""
STRAY.component = "Gnc.Stray"


def _entry(tuple_: Any) -> dict[str, Any]:
    """A parameters tuple as the record holds it: each field by name, an array as nested lists.

    Args:
        tuple_: the tuple.

    Returns:
        The entry.
    """
    return {name: np.asarray(value).tolist() for name, value in tuple_._asdict().items()}


def _configuration_s(algorithm_parameters: dict[str, Any], dictionary: Dictionary) -> list[Any]:
    """The tuples of the algorithm instances a configuration's dictionary holds.

    Args:
        algorithm_parameters: each algorithm component's tuple.
        dictionary: the configuration's dictionary.

    Returns:
        The tuples.
    """
    return [algorithm_parameters[i.component] for i in dictionary.algorithm_instances()]


def test_the_record_holds_every_field_under_the_instance_s_qualified_name(
    tmp_path: Path, algorithm_parameters: dict[str, Any]
):
    """Each tuple is keyed by its component's FPP-qualified instance, each value as JSON numbers.

    Args:
        tmp_path: where the case's files are written.
        algorithm_parameters: each algorithm component's tuple.
    """
    tuples = list(algorithm_parameters.values())
    assert tuples

    record = parameters.write(tuples, tmp_path / "run_0000.prm.json")

    assert record == tmp_path / "run_0000.prm.json"
    assert json.loads(record.read_text()) == {
        gnc_instance(component).name: _entry(tuple_)
        for component, tuple_ in algorithm_parameters.items()
    }


def test_the_record_holds_each_tuple_under_its_own_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, algorithm_parameters: dict[str, Any]
):
    """A toy component's tuple is written beside the algorithms', under its own instance's name.

    Args:
        tmp_path: where the case's files are written.
        monkeypatch: gives the GNC sub-topologies the toy component's instance.
        algorithm_parameters: each algorithm component's tuple.
    """
    other = Instance("Other.stray", "Gnc.Stray", 0x2000)
    instances = (*gnc_instances(), other)
    monkeypatch.setattr("fsw.codegen.deployment.gnc_instances", lambda: instances)

    record = parameters.write(
        [*algorithm_parameters.values(), STRAY(gain=0.5)], tmp_path / "run_0000.prm.json"
    )

    entries = json.loads(record.read_text())
    expected = {gnc_instance(component).name for component in algorithm_parameters}
    assert entries.keys() == {*expected, "Other.stray"}
    assert entries["Other.stray"] == {"gain": 0.5}


def test_two_tuples_of_one_component_are_refused_naming_its_instance(
    tmp_path: Path, algorithm_parameters: dict[str, Any]
):
    """Both would be written under one instance, so neither is; the record is not written.

    Args:
        tmp_path: where the case's files are written.
        algorithm_parameters: each algorithm component's tuple.
    """
    for component, tuple_ in algorithm_parameters.items():
        instance = gnc_instance(component).name
        with pytest.raises(ValueError, match=re.escape(instance)):
            parameters.write([tuple_, tuple_], tmp_path / "run_0000.prm.json")

        assert not (tmp_path / "run_0000.prm.json").exists()


def test_a_component_instanced_nowhere_is_refused(tmp_path: Path):
    """A tuple whose component no GNC sub-topology instances names it, and writes nothing.

    Args:
        tmp_path: where the case's files are written.
    """
    with pytest.raises(ValueError, match=r"Gnc\.Stray is instanced 0 times"):
        parameters.write([STRAY(gain=1.0)], tmp_path / "run_0000.prm.json")

    assert not (tmp_path / "run_0000.prm.json").exists()


def test_f_prime_s_tool_makes_the_dat_beside_the_record_and_decodes_it_back(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    configuration: str,
    dictionary: Dictionary,
    algorithm_parameters: dict[str, Any],
):
    """The `.dat` decodes, with `-o` so the record is never overwritten, to the record's values.

    Making it prints nothing, so a campaign's output carries no line per case.

    Args:
        tmp_path: where the case's files are written.
        capsys: captures what making the `.dat` prints.
        configuration: the configuration, whose dictionary the `.dat` is made against.
        dictionary: that dictionary.
        algorithm_parameters: each algorithm component's tuple.
    """
    tuples = _configuration_s(algorithm_parameters, dictionary)
    record = parameters.write(tuples, tmp_path / "run_0000.prm.json")
    written = record.read_text()

    dat = parameters.dat(record, dictionary_path(configuration))

    assert capsys.readouterr().out == ""
    assert dat == tmp_path / "run_0000.prm.dat"
    decoded = tmp_path / "decoded.json"
    tool = Path(sys.executable).parent / "fprime-prm-decode"
    command = [tool, dat, "-d", dictionary_path(configuration), "-o", decoded]
    subprocess.run(command, check=True, capture_output=True)
    assert json.loads(decoded.read_text()) == json.loads(written)
    assert record.read_text() == written


def test_a_record_naming_a_parameter_the_dictionary_lacks_makes_no_dat(
    tmp_path: Path,
    configuration: str,
    dictionary: Dictionary,
    algorithm_parameters: dict[str, Any],
):
    """F´'s tool refuses it with its own error, naming the parameter.

    Args:
        tmp_path: where the case's files are written.
        configuration: the configuration, whose dictionary the `.dat` is made against.
        dictionary: that dictionary.
        algorithm_parameters: each algorithm component's tuple.
    """
    record = parameters.write(
        _configuration_s(algorithm_parameters, dictionary), tmp_path / "run_0000.prm.json"
    )
    entries = json.loads(record.read_text())
    instance = sorted(entries)[0]
    entries[instance]["notAParameter"] = 1.0
    record.write_text(json.dumps(entries))

    with pytest.raises(RuntimeError, match=re.escape(f"{instance}.notAParameter")):
        parameters.dat(record, dictionary_path(configuration))

    assert not (tmp_path / "run_0000.prm.dat").exists()
