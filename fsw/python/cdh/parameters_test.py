"""The Python build's CDH reads its instance's parameters from the case's record."""

import json
from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.fpp_types import Gnc
from fsw.python.cdh import parameters

MOUNTING = [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
"""A mounting [PB] that is not symmetric, so a transposed one shows."""


def _record(directory: Path, entries: dict) -> Path:
    """A case's record, written by hand.

    Args:
        directory: where to write it.
        entries: the JSON object.

    Returns:
        Its path.
    """
    path = directory / "run_0000.prm.json"
    path.write_text(json.dumps(entries))
    return path


def test_the_instance_s_parameters_come_back_as_its_tuple(tmp_path: Path):
    """Keyed by nav's qualified instance, as the ground writes it, an array as a float64 array.

    Args:
        tmp_path: where the record is written.
    """
    record = _record(tmp_path, {"ImuDeadReckoning.nav": {"mu": 3.986004360e14, "dcm_PB": MOUNTING}})

    read = parameters.read(record, Gnc.ImuDeadReckonerParameters)

    assert type(read) is Gnc.ImuDeadReckonerParameters
    assert read.mu == 3.986004360e14
    assert isinstance(read.dcm_PB, np.ndarray)
    assert read.dcm_PB.dtype == np.float64
    np.testing.assert_array_equal(read.dcm_PB, MOUNTING)


def test_a_parameter_missing_from_the_record_raises(tmp_path: Path):
    """A record without `dcm_PB` fails, as the F´ build's boot does.

    Args:
        tmp_path: where the record is written.
    """
    record = _record(tmp_path, {"ImuDeadReckoning.nav": {"mu": 3.986004360e14}})

    with pytest.raises(TypeError, match="dcm_PB"):
        parameters.read(record, Gnc.ImuDeadReckonerParameters)


def test_a_parameter_the_component_lacks_raises(tmp_path: Path):
    """A record naming a field the tuple lacks fails, as F´'s tool does.

    Args:
        tmp_path: where the record is written.
    """
    record = _record(
        tmp_path,
        {"ImuDeadReckoning.nav": {"mu": 3.986004360e14, "dcm_PB": MOUNTING, "gain": 1.0}},
    )

    with pytest.raises(TypeError, match="gain"):
        parameters.read(record, Gnc.ImuDeadReckonerParameters)


def test_a_record_without_the_instance_raises_naming_it(tmp_path: Path):
    """An entry for nav under another qualified name is not nav's.

    Args:
        tmp_path: where the record is written.
    """
    record = _record(tmp_path, {"Other.nav": {"mu": 3.986004360e14, "dcm_PB": MOUNTING}})

    with pytest.raises(KeyError, match=r"no parameters for ImuDeadReckoning\.nav"):
        parameters.read(record, Gnc.ImuDeadReckonerParameters)
