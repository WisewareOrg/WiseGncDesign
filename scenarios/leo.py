"""How each scenario a TST item references is flown.

A TST item says in words what a scenario evaluates, and its reference names one of these
definitions. A definition is the scenario's ground procedure, an `async def` the ground runs from
t = 0 against the flight software, and its `sim_` marks are the rest of how it is flown:
`mission_tests` puts them on each test it generates, beside the mission's vehicle, and
`sim_ground_period_s` sets the ground's period. A different procedure, duration, case count or
WiseDynamics scenario is a different definition, referenced by a different TST item.
"""

import pytest

from harness.ground import Ground


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s(5700.0)
@pytest.mark.sim_runs(460)
async def leo500(ground: Ground) -> None:
    """The 500 km, 45 degree orbit; nav is initialized from tracking 60 s after boot.

    Args:
        ground: the ground the procedure runs on.
    """
    await initialize_nav_from_tracking(ground, after_s=60.0)


@pytest.mark.sim_scenario("leo400")
@pytest.mark.sim_duration_s(5700.0)
@pytest.mark.sim_runs(460)
async def leo400(ground: Ground) -> None:
    """The 400 km, 45 degree orbit; nav is initialized from tracking 60 s after boot.

    Args:
        ground: the ground the procedure runs on.
    """
    await initialize_nav_from_tracking(ground, after_s=60.0)


async def initialize_nav_from_tracking(ground: Ground, *, after_s: float) -> None:
    """Waits, gives nav the tracked state as of now, and waits for nav to leave idle.

    Args:
        ground: the ground the procedure runs on.
        after_s: s, how long to wait first.
    """
    await ground.sleep(after_s)
    truth = ground.truth()
    await ground.send(
        "nav.initNavState",
        epoch=ground.now_s,
        attitude=truth["q_BN"],
        position=truth["r_N"],
        velocity=truth["v_N"],
    )
    await ground.until(lambda: ground.tlm("nav.navState") not in (None, "idle"), timeout_s=5.0)
