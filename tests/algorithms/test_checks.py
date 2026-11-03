"""Every `check_*` of every literate algorithm module passes."""

import pytest

from gnc_algorithms import imu_dead_reckoning, mrp


@pytest.mark.parametrize("module", [imu_dead_reckoning, mrp], ids=lambda m: m.__name__)
def test_every_check_passes(module):
    module.run_checks()
