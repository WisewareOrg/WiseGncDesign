"""One error metric of a run."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from gnc_analysis.runs import Run

__all__ = ["Metric"]


@dataclass(frozen=True)
class Metric:
    """One error metric of a run against truth.

    Attributes:
        label: the metric's name, such as "attitude error".
        unit: the unit of its values, such as "deg".
        rate_unit: the unit of its growth rate, `unit` per second, such as "deg/s".
        compute: maps a run to the metric at every sample, an (N,) array in `unit`.
    """

    label: str
    unit: str
    rate_unit: str
    compute: Callable[[Run], np.ndarray]
