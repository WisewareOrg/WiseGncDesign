"""Both builds' RK4 step against known solutions, SciPy's `solve_ivp` and each other.

The C++ step's checks are skipped without the extension `just fsw` builds.
"""

from collections.abc import Callable

import numpy as np
import pytest
from numba import njit
from scipy.integrate import solve_ivp

from algorithms.utils.rk4 import step

MU = 1.0
"""The orbit's gravitational parameter."""
A, E = 1.0, 0.5
"""The orbit's semi-major axis and eccentricity."""
R_P = A * (1 - E)
"""The orbit's periapsis radius."""
Y0 = np.array([R_P, 0.0, 0.0, 0.0, np.sqrt(MU * (1 + E) / R_P), 0.0])
"""The orbit's state at periapsis, (r, v)."""
PERIOD = 2 * np.pi * np.sqrt(A**3 / MU)
"""The orbit's period."""


@njit(cache=True)
def oscillator(t: float, y: np.ndarray) -> np.ndarray:
    """The unit harmonic oscillator x'' = -x, as y = (x, v).

    Args:
        t: time, s; unused.
        y: (2,) position and velocity.

    Returns:
        (2,) dy/dt.
    """
    return np.array([y[1], -y[0]])


@njit(cache=True)
def cubic(t: float, y: np.ndarray) -> np.ndarray:
    """The right-hand side of y' = t^3, which depends on t alone.

    Args:
        t: time, s.
        y: (1,) state; unused.

    Returns:
        (1,) dy/dt.
    """
    return np.array([t**3])


@njit(cache=True)
def kepler(t: float, y: np.ndarray, mu: float) -> np.ndarray:
    """Two-body motion r'' = -mu r / |r|^3, as y = (r, v).

    Args:
        t: time, s; unused.
        y: (6,) position and velocity.
        mu: gravitational parameter.

    Returns:
        (6,) dy/dt.
    """
    r = y[:3]
    return np.concatenate((y[3:], -mu * r / np.linalg.norm(r) ** 3))


@njit
def fly_oscillator(y: np.ndarray, h: float, n: int) -> np.ndarray:
    """N steps of the oscillator from t = 0, from compiled code.

    Args:
        y: (2,) initial state.
        h: step, s.
        n: number of steps.

    Returns:
        (2,) state at t = n h.
    """
    for k in range(n):
        y = step(oscillator, k * h, y, h)
    return y


def cpp_step(fun: Callable[..., np.ndarray], t: float, y: np.ndarray, h: float, *args: object):
    """`Rk4.hpp`'s step through its extension, called as the Python step is.

    Args:
        fun: the right-hand side, `fun(t, y, *args)`.
        t: the time at the start of the step.
        y: the state at t.
        h: the step.
        *args: passed through to fun after y.

    Returns:
        The state at t + h.
    """
    from algorithms.utils.rk4 import _rk4

    return _rk4.step(lambda t, y: fun(t, y, *args), t, y, h)


@pytest.fixture
def cpp() -> Callable[..., np.ndarray]:
    """The C++ step, `step(fun, t, y, h, *args)`; skips without its build.

    Returns:
        `cpp_step`.
    """
    try:
        from algorithms.utils.rk4 import _rk4  # noqa: F401
    except ImportError:
        pytest.skip("the F´ build of the RK4 step is absent; run `just fsw`")
    return cpp_step


@pytest.fixture(params=["python", "cpp"])
def rk4(request: pytest.FixtureRequest) -> Callable[..., np.ndarray]:
    """Each build's step, `step(fun, t, y, h, *args)`; skips the C++ one without its build.

    Args:
        request: the build, `python` or `cpp`.

    Returns:
        The build's step.
    """
    return step if request.param == "python" else request.getfixturevalue("cpp")


def fly(rk4: Callable[..., np.ndarray], fun: Callable, y: np.ndarray, h: float, n: int, *args):
    """N steps from t = 0.

    Args:
        rk4: the build's step.
        fun: the right-hand side.
        y: the initial state.
        h: the step.
        n: number of steps.
        *args: passed through to fun after y.

    Returns:
        The state at t = n h.
    """
    for k in range(n):
        y = rk4(fun, k * h, y, h, *args)
    return y


def test_the_global_error_shrinks_as_h_to_the_fourth(rk4: Callable[..., np.ndarray]):
    """Halving h divides the oscillator's error at t = 10 by 2^4.

    Args:
        rk4: the build's step.
    """
    t_end = 10.0
    exact = np.array([np.cos(t_end), -np.sin(t_end)])
    errors = [
        np.linalg.norm(fly(rk4, oscillator, np.array([1.0, 0.0]), t_end / n, n) - exact)
        for n in (100, 200, 400)
    ]
    orders = np.log2(np.array(errors[:-1]) / np.array(errors[1:]))
    np.testing.assert_allclose(orders, 4.0, atol=0.05)


def test_each_stage_is_taken_at_its_own_time(rk4: Callable[..., np.ndarray]):
    """One step of y' = t^3 from t = 1 is exact, as RK4 is Simpson's rule for a cubic in t alone.

    Args:
        rk4: the build's step.
    """
    t0, h = 1.0, 0.5
    np.testing.assert_allclose(
        rk4(cubic, t0, np.array([0.0]), h), [((t0 + h) ** 4 - t0**4) / 4], rtol=1e-15
    )


def test_an_orbit_matches_solve_ivp(rk4: Callable[..., np.ndarray]):
    """One period of an e = 0.5 orbit, mu passed through, ends at DOP853's state and at Y0.

    Args:
        rk4: the build's step.
    """
    y = fly(rk4, kepler, Y0, PERIOD / 4000, 4000, MU)
    expected = solve_ivp(
        kepler, (0.0, PERIOD), Y0, method="DOP853", rtol=1e-13, atol=1e-13, args=(MU,)
    ).y[:, -1]
    np.testing.assert_allclose(y, expected, rtol=0, atol=1e-8)
    np.testing.assert_allclose(y, Y0, rtol=0, atol=1e-8)


def test_the_builds_fly_an_orbit_alike(cpp: Callable[..., np.ndarray]):
    """The C++ step flies one period of the orbit to the Python step's state.

    Args:
        cpp: the C++ step.
    """
    n = 1000
    np.testing.assert_allclose(
        fly(cpp, kepler, Y0, PERIOD / n, n, MU),
        fly(step, kepler, Y0, PERIOD / n, n, MU),
        rtol=0,
        atol=1e-11,
    )


def test_the_python_step_runs_from_compiled_code():
    """Compiled code calling the step flies the oscillator to the state Python calling it does."""
    y0, h, n = np.array([1.0, 0.0]), 0.05, 200
    np.testing.assert_array_equal(fly_oscillator(y0, h, n), fly(step, oscillator, y0, h, n))
