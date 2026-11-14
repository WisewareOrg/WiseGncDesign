"""Fixtures every package's tests share: an F´ copy and its station, a case's parameters and IDs.

A test module flying other values overrides `nav_parameters`. The `.dat` and the IDs need the F´
build, which the tests that ask for them skip without. The copy and its station need it too, and a
test asking for either skips without it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import numpy as np
import pytest

from fsw.codegen.fpp_types import Gnc
from ground import parameters
from ground.dictionary import Dictionary
from lab import DICTIONARY

if TYPE_CHECKING:
    from ground.fprime_station import FprimeStation


@pytest.fixture
def fsw() -> ModuleType:
    """A fresh copy of the deployment, not yet booted; skips the test without the F´ build.

    Returns:
        The copy.
    """
    if importlib.util.find_spec("lab._wise_fsw") is None:
        pytest.skip("the F´ build is absent; run `just fsw`")
    from lab.power_cycle import power_cycle

    return power_cycle()


@pytest.fixture
def station(fsw: ModuleType) -> FprimeStation:
    """The ground station on the test's copy, on the dictionary the build generated.

    Args:
        fsw: the test's copy.

    Returns:
        The station.
    """
    from ground.dictionary import Dictionary
    from ground.fprime_station import FprimeStation
    from lab import DICTIONARY

    return FprimeStation(fsw, Dictionary(DICTIONARY))


@pytest.fixture
def nav_parameters() -> Gnc.ImuDeadReckonerParameters:
    """Nav's parameters a case flies with: Earth's mu, the IMU mounted at identity.

    Returns:
        The tuple.
    """
    return Gnc.ImuDeadReckonerParameters(mu=3.986004360e14, dcm_PB=np.eye(3))


@pytest.fixture
def prm_record(nav_parameters: Gnc.ImuDeadReckonerParameters, tmp_path: Path) -> Path:
    """A case's parameter record, written as the ground writes it, in a case directory of its own.

    Args:
        nav_parameters: nav's parameters.
        tmp_path: the test's directory, which holds the case directory `case`.

    Returns:
        The record, `case/run_0000.prm.json`.
    """
    case = tmp_path / "case"
    case.mkdir()
    return parameters.write(nav_parameters, case / "run_0000.prm.json")


@pytest.fixture
def prm(prm_record: Path) -> str:
    """The case's `.dat`, made beside its record as the F´ host makes it.

    Args:
        prm_record: the case's record.

    Returns:
        The `.dat`'s path, as `boot` takes it.
    """
    return str(parameters.dat(prm_record, DICTIONARY))


@pytest.fixture(scope="session")
def parameter_ids() -> list[int]:
    """Every parameter's ID in the deployment's dictionary, which `boot` holds valid.

    Returns:
        The IDs, sorted.
    """
    return sorted(Dictionary(DICTIONARY).parameters_by_id)
