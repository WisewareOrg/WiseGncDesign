"""The ground's parameter record of a case, and the `.dat` F´'s own tool makes from it."""

import json
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.fpp_types import Gnc
from ground import parameters
from lab import DICTIONARY

NAV = Gnc.ImuDeadReckonerParameters(
    mu=3.986004360e14, dcm_PB=np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
)
"""Nav's parameters, with a mounting that is not symmetric, so a transposed one shows."""


def test_the_record_holds_every_field_under_the_instance_s_qualified_name(tmp_path: Path):
    """The JSON is keyed by nav's FPP-qualified instance, each field's value as JSON numbers.

    Args:
        tmp_path: where the case's files are written.
    """
    record = parameters.write(NAV, tmp_path / "run_0000.prm.json")

    assert record == tmp_path / "run_0000.prm.json"
    assert json.loads(record.read_text()) == {
        "ImuDeadReckoning.nav": {
            "mu": 3.986004360e14,
            "dcm_PB": [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        }
    }


def test_a_component_instanced_nowhere_is_refused(tmp_path: Path):
    """A tuple whose component no GNC sub-topology instances names it, and writes nothing.

    Args:
        tmp_path: where the case's files are written.
    """
    stray = namedtuple("StrayParameters", ["gain"])
    stray.component = "Gnc.Stray"

    with pytest.raises(ValueError, match=r"Gnc\.Stray is instanced 0 times"):
        parameters.write(stray(gain=1.0), tmp_path / "run_0000.prm.json")

    assert not (tmp_path / "run_0000.prm.json").exists()


@pytest.mark.skipif(not DICTIONARY.exists(), reason="the F´ build is absent; run `just fsw`")
def test_f_prime_s_tool_makes_the_dat_beside_the_record_and_decodes_it_back(tmp_path: Path):
    """The `.dat` decodes, with `-o` so the record is never overwritten, to the record's values.

    Args:
        tmp_path: where the case's files are written.
    """
    record = parameters.write(NAV, tmp_path / "run_0000.prm.json")
    written = record.read_text()

    dat = parameters.dat(record, DICTIONARY)

    assert dat == tmp_path / "run_0000.prm.dat"
    decoded = tmp_path / "decoded.json"
    tool = Path(sys.executable).parent / "fprime-prm-decode"
    subprocess.run([tool, dat, "-d", DICTIONARY, "-o", decoded], check=True, capture_output=True)
    assert json.loads(decoded.read_text()) == json.loads(written)
    assert record.read_text() == written


@pytest.mark.skipif(not DICTIONARY.exists(), reason="the F´ build is absent; run `just fsw`")
def test_a_record_naming_a_parameter_the_dictionary_lacks_makes_no_dat(tmp_path: Path):
    """F´'s tool refuses it, and the error carries what the tool said.

    Args:
        tmp_path: where the case's files are written.
    """
    record = parameters.write(NAV, tmp_path / "run_0000.prm.json")
    entries = json.loads(record.read_text())
    entries["ImuDeadReckoning.nav"]["gain"] = 1.0
    record.write_text(json.dumps(entries))

    with pytest.raises(RuntimeError, match=r"ImuDeadReckoning\.nav\.gain"):
        parameters.dat(record, DICTIONARY)

    assert not (tmp_path / "run_0000.prm.dat").exists()
