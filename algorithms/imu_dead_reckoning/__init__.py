"""The IMU dead reckoner: its notebook (derivation, estimator, mission), gross check and tests.

`parity.py`, a second notebook, holds its Python and F´ builds to parity.

`ImuDeadReckoner` and `dead_reckoner` import from here. They live in the notebook,
`imu_dead_reckoning.py`, imported on first use so that importing `gross_check` alone, as the
notebook itself does, does not run the notebook a second time.
"""

__all__ = ["ImuDeadReckoner", "dead_reckoner"]


def __getattr__(name: str) -> object:
    """Import the notebook on first use of a name it defines.

    Args:
        name: the attribute asked for.

    Returns:
        The notebook's attribute of that name.

    Raises:
        AttributeError: the name is not one this package exports.
    """
    if name in __all__:
        from algorithms.imu_dead_reckoning import imu_dead_reckoning

        return getattr(imu_dead_reckoning, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
