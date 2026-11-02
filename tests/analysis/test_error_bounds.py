"""`gnc_analysis.error_bounds` on synthetic runs: the growth's shape, and the ratio's response to
an injected error."""

import numpy as np
import pytest

from gnc_analysis.error_bounds import bound_ratios, error_growth
from gnc_analysis.runs import load_run

NOISE = {"gyro_noise_std_rad_s": 5e-5, "accel_noise_std_m_s2": 5e-5, "step_s": 1.0}
MU = 3.986004418e14  # m^3/s^2, Earth
METRICS = {"attitude error [rad]", "velocity error [m/s]", "position error [m]"}


def test_each_metric_has_an_error_and_a_growth_over_t_s(run_file):
    run = load_run(run_file())

    growths = error_growth(run, mu=MU, **NOISE)

    assert set(growths) == METRICS
    for error, growth in growths.values():
        assert error.shape == growth.shape == run.t_s.shape


def test_each_growth_starts_at_zero_and_increases(run_file):
    growths = error_growth(load_run(run_file()), mu=MU, **NOISE)

    for name, (_, growth) in growths.items():
        assert growth[0] == 0.0, name
        assert np.all(np.diff(growth) > 0.0), name


def test_the_gravity_gradient_factor_raises_translational_growth(run_file):
    run = load_run(run_file())

    with_gravity = error_growth(run, mu=MU, **NOISE)
    without_gravity = error_growth(run, mu=0.0, **NOISE)

    for name in ("velocity error [m/s]", "position error [m]"):
        assert np.all(with_gravity[name][1][1:] > without_gravity[name][1][1:]), name
    np.testing.assert_array_equal(
        with_gravity["attitude error [rad]"][1], without_gravity["attitude error [rad]"][1]
    )


@pytest.mark.parametrize("name", ["velocity error [m/s]", "position error [m]"])
def test_a_ratio_scales_with_the_injected_error(run_file, name):
    slow = load_run(run_file(case=0, position_drift_rate_m_s=0.5))
    fast = load_run(run_file(case=1, position_drift_rate_m_s=1.0))

    np.testing.assert_allclose(
        bound_ratios(fast, mu=MU, **NOISE)[name],
        2.0 * bound_ratios(slow, mu=MU, **NOISE)[name],
        rtol=1e-12,
    )
