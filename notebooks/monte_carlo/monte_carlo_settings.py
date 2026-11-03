"""What one Monte Carlo run of a scenario runs, read from the environment."""

import os
from dataclasses import dataclass

__all__ = ["MonteCarloSettings"]

RUNS_VARIABLE = "GNC_MONTE_CARLO_RUNS"
WORKERS_VARIABLE = "GNC_MONTE_CARLO_WORKERS"
DEFAULT_RUNS = 852


def _positive_int(variable: str, default: int) -> int:
    text = os.environ.get(variable)
    if text is None:
        return default
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"{variable} must be a positive integer, got {text!r}")
    return value


@dataclass(frozen=True)
class MonteCarloSettings:
    """One Monte Carlo run: `runs` cases on `workers` pytest-xdist workers, from session seed
    `seed`, each case simulating `duration_s` seconds."""

    runs: int
    workers: int
    seed: int
    duration_s: float

    @classmethod
    def from_environment(cls, seed: int, duration_s: float) -> "MonteCarloSettings":
        """The settings with the case count from `GNC_MONTE_CARLO_RUNS` (default 852) and the
        worker count from `GNC_MONTE_CARLO_WORKERS` (default the CPU count).

        Raises:
            ValueError: naming a variable set to anything but a positive integer.
        """
        return cls(
            runs=_positive_int(RUNS_VARIABLE, DEFAULT_RUNS),
            workers=_positive_int(WORKERS_VARIABLE, os.cpu_count() or 1),
            seed=seed,
            duration_s=duration_s,
        )

    def line(self) -> str:
        """The one line printed before the cases run."""
        return (
            f"monte carlo: {self.runs} runs, {self.workers} workers, seed {self.seed}, "
            f"{self.duration_s:g} s per case"
        )
