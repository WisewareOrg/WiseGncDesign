"""The ground's parameter record of a case, and the `.dat` F´'s own tool makes from it.

The parameters are every algorithm component's, generated from the contract, and the `.dat` is
made against each configuration's dictionary.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ground import parameters
from ground.dictionary import Dictionary
from lab import dictionary_path


def _entry(tuple_: Any) -> dict[str, Any]:
    """A parameters tuple as the record holds it: each field by name, an array as nested lists.

    Args:
        tuple_: the tuple.

    Returns:
        The entry.
    """
    return {name: np.asarray(value).tolist() for name, value in tuple_._asdict().items()}


def _configuration_s(
    algorithm_parameters: dict[str, Any], dictionary: Dictionary
) -> dict[str, Any]:
    """The tuples of the algorithm instances a configuration's dictionary holds.

    Args:
        algorithm_parameters: each algorithm component's tuple.
        dictionary: the configuration's dictionary.

    Returns:
        Each instance's tuple, by its qualified name.
    """
    return {i.name: algorithm_parameters[i.component] for i in dictionary.algorithm_instances()}


def test_the_record_holds_every_field_under_the_instance_it_is_keyed_by(
    tmp_path: Path, algorithm_parameters: dict[str, Any]
):
    """Each tuple is written under its key, a qualified instance, each value as JSON numbers.

    Args:
        tmp_path: where the case's files are written.
        algorithm_parameters: each algorithm component's tuple.
    """
    tuples = {
        f"MockConfiguration.mock{n}": tuple_
        for n, tuple_ in enumerate(algorithm_parameters.values())
    }
    assert tuples

    record = parameters.write(tuples, tmp_path / "run_0000.prm.json")

    assert record == tmp_path / "run_0000.prm.json"
    assert json.loads(record.read_text()) == {
        instance: _entry(tuple_) for instance, tuple_ in tuples.items()
    }


def test_f_prime_s_tool_makes_the_dat_beside_the_record_and_decodes_it_back(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fprime_configuration: str,
    dictionary: Dictionary,
    algorithm_parameters: dict[str, Any],
):
    """The `.dat` decodes, with `-o` so the record is never overwritten, to the record's values.

    Making it prints nothing, so a campaign's output carries no line per case.

    Args:
        tmp_path: where the case's files are written.
        capsys: captures what making the `.dat` prints.
        fprime_configuration: the configuration, whose dictionary the `.dat` is made against.
        dictionary: that dictionary.
        algorithm_parameters: each algorithm component's tuple.
    """
    tuples = _configuration_s(algorithm_parameters, dictionary)
    record = parameters.write(tuples, tmp_path / "run_0000.prm.json")
    written = record.read_text()

    dat = parameters.dat(record, dictionary_path(fprime_configuration))

    assert capsys.readouterr().out == ""
    assert dat == tmp_path / "run_0000.prm.dat"
    decoded = tmp_path / "decoded.json"
    tool = Path(sys.executable).parent / "fprime-prm-decode"
    command = [tool, dat, "-d", dictionary_path(fprime_configuration), "-o", decoded]
    subprocess.run(command, check=True, capture_output=True)
    assert json.loads(decoded.read_text()) == json.loads(written)
    assert record.read_text() == written


def test_a_record_naming_a_parameter_the_dictionary_lacks_makes_no_dat(
    tmp_path: Path,
    fprime_configuration: str,
    dictionary: Dictionary,
    algorithm_parameters: dict[str, Any],
):
    """F´'s tool refuses it with its own error, naming the parameter.

    Args:
        tmp_path: where the case's files are written.
        fprime_configuration: the configuration, whose dictionary the `.dat` is made against.
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
        parameters.dat(record, dictionary_path(fprime_configuration))

    assert not (tmp_path / "run_0000.prm.dat").exists()
