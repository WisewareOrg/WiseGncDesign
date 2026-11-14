"""Fixtures every package's tests share: a case's parameter record, its `.dat` and the IDs to boot.

A test module flying other values overrides `nav_parameters`. The `.dat` and the IDs need the F´
build's dictionary, so a test asking for either skips without it. Every pytest run loads this file,
the judge's included, so the FPP model, Basilisk and F´ are imported only by the fixtures that need
them.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from fsw.codegen.fpp_types import Gnc


@pytest.fixture
def nav_parameters() -> Gnc.ImuDeadReckonerParameters:
    """Nav's parameters a case flies with: Earth's mu, the IMU mounted at identity.

    Returns:
        The tuple.
    """
    from fsw.codegen.fpp_types import Gnc

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
    from ground import parameters

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
    from ground import parameters

    return str(parameters.dat(prm_record, _dictionary()))


@pytest.fixture(scope="session")
def parameter_ids() -> list[int]:
    """Every parameter's ID in the deployment's dictionary, which `boot` holds valid.

    Returns:
        The IDs, sorted.
    """
    from ground.dictionary import Dictionary

    return sorted(Dictionary(_dictionary()).parameters_by_id)


def _dictionary() -> Path:
    """The deployment's dictionary, skipping the test asking when `just fsw` has not built it.

    Returns:
        Its path.
    """
    from lab import DICTIONARY

    if not DICTIONARY.exists():
        pytest.skip("the F´ build is absent; run `just fsw`")
    return DICTIONARY
