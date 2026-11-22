"""The classic fourth-order Runge–Kutta step, compiled with numba.

For dy/dt = f(t, y), one step of size h is

    k1 = f(t, y)
    k2 = f(t + h/2, y + h/2 k1)
    k3 = f(t + h/2, y + h/2 k2)
    k4 = f(t + h, y + h k3)
    y(t + h) ≈ y + h/6 (k1 + 2 k2 + 2 k3 + k4)

Its local error is O(h^5) and its global error O(h^4).

Numba types each right-hand side by its identity in the running process, so `step` compiles once
per right-hand side per process, and neither it nor any compiled caller passing it a right-hand
side can be cached to disk.
"""

from collections.abc import Callable

import numpy as np
from numba import njit

__all__ = ["step"]


@njit
def step(fun: Callable[..., np.ndarray], t: float, y: np.ndarray, h: float, *args: object) -> np.ndarray:
    """One RK4 step of dy/dt = fun(t, y, *args) from t to t + h.

    Args:
        fun: the right-hand side, a numba-compiled `fun(t, y, *args)` returning dy/dt shaped
            like y, as SciPy's `solve_ivp` takes it.
        t: the time at the start of the step.
        y: the state at t.
        h: the step.
        *args: passed through to fun after y.

    Returns:
        The state at t + h.
    """
    k1 = fun(t, y, *args)
    k2 = fun(t + 0.5 * h, y + 0.5 * h * k1, *args)
    k3 = fun(t + 0.5 * h, y + 0.5 * h * k2, *args)
    k4 = fun(t + h, y + h * k3, *args)
    return y + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
