"""The dead reckoner's case parameters: nav's own, which a test module flying others overrides."""

import numpy as np
import pytest

from fsw.codegen.fpp_types import Gnc


@pytest.fixture
def nav_parameters() -> Gnc.ImuDeadReckonerParameters:
    """Nav's parameters a case flies with: Earth's mu, the IMU mounted at identity.

    Returns:
        The tuple.
    """
    return Gnc.ImuDeadReckonerParameters(mu=3.986004360e14, dcm_PB=np.eye(3))


@pytest.fixture
def case_parameters(
    nav_parameters: Gnc.ImuDeadReckonerParameters,
) -> tuple[Gnc.ImuDeadReckonerParameters]:
    """The case's parameters: nav's alone.

    Args:
        nav_parameters: nav's parameters.

    Returns:
        Nav's tuple.
    """
    return (nav_parameters,)
