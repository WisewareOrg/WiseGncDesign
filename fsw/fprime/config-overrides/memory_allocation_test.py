"""F´'s allocator, `MemoryAllocation.hpp`, gives memory until the deployment first steps.

Flown on the test mock `MockActuation`, whose `actuator.allocate` asks the registered allocator for
memory. Skipped without the deployment `just fsw` builds, as `mock_actuation` skips.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from fsw.mock import MOCK
from ground.fprime_station import FprimeStation
from lab import Adapter

if TYPE_CHECKING:
    from conftest import MockActuationCase

NS = 1_000_000_000
"""ns per s."""


def test_an_allocation_after_the_first_step_asserts(mock_actuation: MockActuationCase) -> None:
    """The tick that asks for memory, the one after the first, raises the allocator's assert.

    Args:
        mock_actuation: the configuration and its record.
    """
    adapter = Adapter(mock_actuation.configuration, mock_actuation.record, contract=MOCK)
    adapter.boot()
    station = FprimeStation(adapter, adapter.dictionary)
    adapter.tick(NS, {})

    station.uplink("actuator.allocate", {}, 1)
    with pytest.raises(RuntimeError, match=r'^Assert: "[^"]*/MemoryAllocation\.hpp:\d+"'):
        adapter.tick(2 * NS, {})
