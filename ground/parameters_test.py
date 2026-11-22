"""The ground's parameter record of a case, and the `.dat` F´'s own tool makes from it.

The parameters are every algorithm component's, generated from the contract, and the `.dat` is
made against each configuration's dictionary.
"""

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.codegen.dictionary import Dictionary
from fsw.codegen.fpp_model import Instance
from ground import parameters
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
    algorithm_parameters: dict[str, Any], instances: tuple[Instance, ...]
) -> dict[str, Any]:
    """The tuples of a configuration's algorithm instances.

    Args:
        algorithm_parameters: each algorithm component's tuple.
        instances: the configuration's algorithm instances.

    Returns:
        Each instance's tuple, by its qualified name.
    """
    return {i.name: algorithm_parameters[i.component] for i in instances}


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
    algorithm_instances: Callable[[str], tuple[Instance, ...]],
    algorithm_parameters: dict[str, Any],
):
    """The `.dat` decodes, with `-o` so the record is never overwritten, to the record's values.

    Making it prints nothing, so a campaign's output carries no line per case.

    Args:
        tmp_path: where the case's files are written.
        capsys: captures what making the `.dat` prints.
        fprime_configuration: the configuration, whose dictionary the `.dat` is made against.
        dictionary: that dictionary, whose absence skips the test.
        algorithm_instances: gives a configuration's algorithm instances.
        algorithm_parameters: each algorithm component's tuple.
    """
    tuples = _configuration_s(algorithm_parameters, algorithm_instances(fprime_configuration))
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
