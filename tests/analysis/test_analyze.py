"""`gnc_analysis`'s error metrics, report and `gnc-analyze` over synthetic runs whose injected
errors have closed forms."""

import numpy as np
import pytest

from gnc_analysis.cli import main
from gnc_analysis.error_metrics import METRICS, summarize
from gnc_analysis.report import analyze
from gnc_analysis.runs import load_run_directory

ATTITUDE_RATES_DEG_S = np.array([0.5, 1.0, 1.5, 2.0, 2.5])  # below 180 deg over the 59 s run
POSITION_RATES_M_S = np.array([0.1, 0.3, 0.2, 0.5, 0.4])
FINAL_T_S = 59.0  # 60 samples at 1 s
FIGURES = {metric.figure_name for metric in METRICS}


@pytest.fixture
def runs_dir(run_directory):
    return run_directory(ATTITUDE_RATES_DEG_S, POSITION_RATES_M_S)


def _stats(final: np.ndarray) -> tuple[float, float, float, float]:
    return final.mean(), final.std(), 3.0 * final.std(), final.max()


def test_summary_matches_the_injected_errors(runs_dir):
    summary = summarize(load_run_directory(runs_dir))
    attitude, position, velocity = summary.metrics

    assert summary.n_runs == 5
    assert summary.duration_s == FINAL_T_S

    expected_attitude = _stats(ATTITUDE_RATES_DEG_S * FINAL_T_S)
    actual_attitude = (
        attitude.final_mean,
        attitude.final_std,
        attitude.final_3sigma,
        attitude.final_max,
    )
    assert actual_attitude == pytest.approx(expected_attitude, rel=1e-3)
    # Every run's error is linear through the origin, so the ensemble RMS is too.
    assert attitude.growth_rate == pytest.approx(
        np.sqrt(np.mean(ATTITUDE_RATES_DEG_S**2)), rel=1e-3
    )

    expected_position = _stats(POSITION_RATES_M_S * FINAL_T_S)
    actual_position = (
        position.final_mean,
        position.final_std,
        position.final_3sigma,
        position.final_max,
    )
    assert actual_position == pytest.approx(expected_position, rel=1e-3)
    assert position.growth_rate == pytest.approx(np.sqrt(np.mean(POSITION_RATES_M_S**2)), rel=1e-3)

    np.testing.assert_allclose(velocity.errors[:, -1], POSITION_RATES_M_S, rtol=1e-12)
    assert velocity.growth_rate == pytest.approx(0.0, abs=1e-12)


def test_analyze_writes_the_summary_and_one_figure_per_metric(runs_dir, tmp_path):
    out_dir = tmp_path / "report"

    summary = analyze(runs_dir, out_dir)

    assert {p.name for p in out_dir.iterdir()} == FIGURES | {"summary.md"}
    text = (out_dir / "summary.md").read_text()
    assert "- Runs: 5" in text
    rate = summary.metrics[0].growth_rate
    assert f"- Growth rate (linear fit of ensemble RMS vs time): {rate:.6f} deg/s" in text


def test_analyze_accepts_one_run_file(run_file, tmp_path):
    summary = analyze(run_file(), tmp_path / "report")

    assert summary.n_runs == 1
    assert summary.metrics[0].final_mean == pytest.approx(2.0 * FINAL_T_S, rel=1e-3)


def test_the_command_returns_zero_on_success(runs_dir, tmp_path):
    assert main([str(runs_dir), "--out", str(tmp_path / "report")]) == 0
    assert (tmp_path / "report" / "summary.md").is_file()


def test_the_command_returns_one_and_names_the_file_on_a_rejected_run(tmp_path, capsys):
    bad = tmp_path / "run_0000.h5"
    bad.write_text("not hdf5")

    assert main([str(bad), "--out", str(tmp_path / "report")]) == 1
    assert f"gnc-analyze: {bad}: could not be opened as HDF5" in capsys.readouterr().err


def test_the_command_exits_two_on_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
