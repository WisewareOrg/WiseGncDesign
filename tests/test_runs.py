import h5py
import numpy as np
import pytest
from gnc_analysis.runs import RunDataError, load_campaign, load_run

from tests.analysis_synthetic import build_campaign, build_run


def test_good_run_loads(tmp_path):
    path = build_run(tmp_path / "run_0000.h5")
    run = load_run(path)

    assert run.case == 0
    assert run.t_s[0] == 0
    assert run.truth_sigma_BN.shape == run.est_sigma_BN.shape


def test_good_campaign_loads(tmp_path):
    directory = build_campaign(tmp_path, n_runs=3)
    runs = load_campaign(directory)

    assert len(runs) == 3
    assert [r.case for r in runs] == [0, 1, 2]


def test_missing_dataset_raises(tmp_path):
    path = build_run(tmp_path / "run_0000.h5")
    with h5py.File(path, "a") as f:
        del f["truth/r_N"]

    with pytest.raises(RunDataError, match="truth/r_N"):
        load_run(path)


def test_wrong_units_raises(tmp_path):
    path = build_run(tmp_path / "run_0000.h5")
    with h5py.File(path, "a") as f:
        f["truth/r_N"].attrs["units"] = "ft"

    with pytest.raises(RunDataError, match="units"):
        load_run(path)


def test_nan_raises(tmp_path):
    path = build_run(tmp_path / "run_0000.h5")
    with h5py.File(path, "a") as f:
        dataset = f["truth/sigma_BN"]
        data = dataset[()]
        data[2, 0] = np.nan
        dataset[...] = data

    with pytest.raises(RunDataError, match="NaN"):
        load_run(path)


def test_missing_case_attr_raises(tmp_path):
    path = build_run(tmp_path / "run_0000.h5")
    with h5py.File(path, "a") as f:
        del f.attrs["case"]

    with pytest.raises(RunDataError, match="case"):
        load_run(path)


def test_missing_seed_attr_raises(tmp_path):
    path = build_run(tmp_path / "run_0000.h5")
    with h5py.File(path, "a") as f:
        del f.attrs["seed"]

    with pytest.raises(RunDataError, match="seed"):
        load_run(path)


def test_mismatched_t_s_raises(tmp_path):
    directory = build_campaign(tmp_path, n_runs=2)
    bad_path = directory / "run_0001.h5"
    with h5py.File(bad_path, "a") as f:
        dataset = f["t_s"]
        # Scaling (rather than shifting) keeps t_s[0] == 0 and strictly increasing, so this run
        # still passes load_run's own per-file checks — only load_campaign's cross-run t_s
        # comparison can catch it.
        dataset[...] = dataset[()] * 1.1

    with pytest.raises(RunDataError, match=r"run_0001\.h5.*t_s differs"):
        load_campaign(directory)
