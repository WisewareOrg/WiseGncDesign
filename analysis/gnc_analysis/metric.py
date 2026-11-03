"""One error metric of a run."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from gnc_analysis.runs import Run

__all__ = ["Metric"]


@dataclass(frozen=True)
class Metric:
    """One error metric: its name, units, per-run computation and figure file name."""

    label: str
    unit: str
    rate_unit: str
    compute: Callable[[Run], np.ndarray]
    figure_name: str
