"""How each scenario a TST item references is flown.

A TST item says in words what a scenario evaluates, and its reference names one of these
definitions. A definition's `sim_` marks are the whole of how it is flown: `mission_tests` puts
them on each test it generates, beside the mission's vehicle. A different duration, case count or
WiseDynamics scenario is a different definition, referenced by a different TST item.
"""

import pytest


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s(5700.0)
@pytest.mark.sim_runs(460)
def leo500() -> None:
    """The 500 km, 45 degree orbit."""


@pytest.mark.sim_scenario("leo400")
@pytest.mark.sim_duration_s(5700.0)
@pytest.mark.sim_runs(460)
def leo400() -> None:
    """The 400 km, 45 degree orbit."""
