"""The faulty test mocks' notebook: a class for `ParameterlessMock` alone, and no `parameters`.

`UnclaimedMock` claims no capability and `ClasslessMock` has no class here, so each of the three
components beside this file seeds one of a mission's lookup failures.
"""

from typing import Any


class ParameterlessMock:
    """A test mock with a parameter that no `parameters` function gives."""

    def __init__(self, parameters: Any) -> None:
        """Takes its parameters.

        Args:
            parameters: its instance's parameters, from the case's record.
        """
