"""Fixtures every package's tests share: a fresh copy of the F´ deployment and its ground station.

Both need the F´ build, so a test asking for either skips without it. Every pytest run loads this
file, the judge's included, so lab and the ground station are imported only by the fixtures that
need them.
"""

from __future__ import annotations

import importlib.util
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

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
