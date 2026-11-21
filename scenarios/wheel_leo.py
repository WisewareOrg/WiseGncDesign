"""How each wheel scenario a TST item references is flown.

As in `leo.py`: a definition is the scenario's ground procedure, and its `sim_` marks are the rest
of how it is flown.
"""

import pytest

from ground.procedures import Ground


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s(5700.0)
@pytest.mark.sim_runs(230)
async def wheel_leo500(ground: Ground) -> None:
    """The 500 km, 45 degree orbit, with no ground procedure: the FSW flies on what it boots with.

    Args:
        ground: the ground the procedure runs on.
    """
