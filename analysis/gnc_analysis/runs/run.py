"""One loaded run."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from gnc_analysis.runs.estimate import Estimate
from gnc_analysis.runs.imu_readings import ImuReadings
from gnc_analysis.runs.truth import Truth

__all__ = ["Run"]


@dataclass(frozen=True)
class Run:
    """One loaded run.

    Attributes:
        path: the file it was read from.
        case: root attr `case`, the run's case index in its session.
        seed: root attr `seed`, the session seed it was drawn from.
        draws: every root attr `draw_<name>`, keyed by `<name>`.
        versions: every root attr `versions_<name>`, keyed by `<name>`.
        t_s: (N,) s, sample times, strictly increasing from 0.
        truth: plant truth at `t_s`.
        est: the flight software's estimate at `t_s`.
        imu: the IMU's output at `t_s`.
    """

    path: Path
    case: int
    seed: int
    draws: Mapping[str, np.ndarray]
    versions: Mapping[str, str]
    t_s: np.ndarray
    truth: Truth
    est: Estimate
    imu: ImuReadings
