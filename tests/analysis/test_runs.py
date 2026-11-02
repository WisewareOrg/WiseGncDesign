"""`load_run` and `load_campaign`: every rule rejects with a message naming the file and the
dataset or attribute, and a good file loads with every value intact."""

import re
from pathlib import Path

import h5py
import numpy as np
import pytest

from gnc_analysis.runs import DATASETS, RunDataError, load_campaign, load_run

README = Path(__file__).resolve().parents[2] / "analysis" / "README.md"


def _rewrite(path: Path, name: str, data, units: str | None = None) -> None:
    with h5py.File(path, "a") as f:
        units = units if units is not None else f[name].attrs["units"]
        del f[name]
        f.create_dataset(name, data=data).attrs["units"] = units


def _values(path: Path, name: str) -> np.ndarray:
    with h5py.File(path, "r") as f:
        return f[name][()]


def _rejects(path: Path, *fragments: str) -> None:
    pattern = ".*".join(re.escape(fragment) for fragment in (str(path), *fragments))
    with pytest.raises(RunDataError, match=pattern):
        load_run(path)


def test_a_good_run_loads_every_dataset_and_attr(run_file):
    path = run_file(case=3, seed=7)

    run = load_run(path)

    assert (run.path, run.case, run.seed) == (path, 3, 7)
    np.testing.assert_array_equal(run.t_s, _values(path, "t_s"))
    loaded = {
        **{f"truth/{k}": getattr(run.truth, k) for k in ("sigma_BN", "omega_BN_B", "r_N", "v_N")},
        **{f"est/{k}": getattr(run.est, k) for k in ("sigma_BN", "r_N", "v_N")},
        **{f"imu/{k}": getattr(run.imu, k) for k in ("gyro_P", "accel_P")},
    }
    assert set(loaded) | {"t_s"} == set(DATASETS)
    for name, value in loaded.items():
        np.testing.assert_array_equal(value, _values(path, name), err_msg=name)
    assert dict(run.versions) == {"wise_gnc_design": "0.0.0"}
    assert set(run.draws) == {"gyro_bias_P", "accel_bias_P"}


def test_a_missing_file_is_rejected(tmp_path):
    _rejects(tmp_path / "run_0000.h5", "does not exist")


def test_a_file_that_is_not_hdf5_is_rejected(tmp_path):
    path = tmp_path / "run_0000.h5"
    path.write_text("not hdf5")
    _rejects(path, "could not be opened as HDF5")


def test_a_missing_dataset_is_rejected(run_file):
    path = run_file()
    with h5py.File(path, "a") as f:
        del f["truth/r_N"]
    _rejects(path, "missing dataset 'truth/r_N'")


def test_wrong_units_are_rejected(run_file):
    path = run_file()
    with h5py.File(path, "a") as f:
        f["truth/r_N"].attrs["units"] = "ft"
    _rejects(path, "'truth/r_N'", "'ft'", "'m'")


def test_a_float32_dataset_is_rejected(run_file):
    path = run_file()
    _rewrite(path, "est/r_N", _values(path, "est/r_N").astype(np.float32))
    _rejects(path, "'est/r_N'", "float32")


def test_a_non_numeric_dataset_is_rejected(run_file):
    path = run_file()
    _rewrite(path, "imu/gyro_P", np.array([b"x"] * 60))
    _rejects(path, "'imu/gyro_P'", "dtype")


@pytest.mark.parametrize(
    ("name", "reshape"),
    [
        ("est/r_N", lambda a: a.reshape(-1)),  # (3N,), not (N, 3)
        ("est/sigma_BN", lambda a: np.hstack([a, a[:, :1]])),  # (N, 4)
        ("t_s", lambda a: a[:, None]),  # (N, 1), not (N,)
    ],
)
def test_a_wrong_shape_is_rejected(run_file, name, reshape):
    path = run_file()
    _rewrite(path, name, reshape(_values(path, name)))
    _rejects(path, f"'{name}'", "shape")


def test_a_row_count_other_than_len_t_s_is_rejected(run_file):
    path = run_file()
    _rewrite(path, "est/r_N", _values(path, "est/r_N")[:-1])
    _rejects(path, "'est/r_N'", "59 rows, expected 60")


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_a_non_finite_value_is_rejected(run_file, bad):
    path = run_file()
    data = _values(path, "truth/sigma_BN")
    data[2, 0] = bad
    _rewrite(path, "truth/sigma_BN", data)
    _rejects(path, "'truth/sigma_BN'", "NaN or inf")


def test_t_s_starting_away_from_zero_is_rejected(run_file):
    path = run_file()
    _rewrite(path, "t_s", _values(path, "t_s") + 1.0)
    _rejects(path, "t_s does not start at 0")


def test_t_s_not_strictly_increasing_is_rejected(run_file):
    path = run_file()
    t_s = _values(path, "t_s")
    t_s[5] = t_s[4]
    _rewrite(path, "t_s", t_s)
    _rejects(path, "t_s is not strictly increasing")


@pytest.mark.parametrize("attr", ["case", "seed"])
def test_a_missing_integer_attr_is_rejected(run_file, attr):
    path = run_file()
    with h5py.File(path, "a") as f:
        del f.attrs[attr]
    _rejects(path, f"missing root attr '{attr}'")


@pytest.mark.parametrize("value", [1.5, "3", np.array([1, 2])])
def test_a_non_integer_case_is_rejected(run_file, value):
    path = run_file()
    with h5py.File(path, "a") as f:
        f.attrs["case"] = value
    _rejects(path, "root attr 'case'", "expected an integer")


def test_a_good_campaign_loads_in_file_order(campaign_dir):
    runs = load_campaign(campaign_dir())

    assert [run.case for run in runs] == [0, 1, 2, 3, 4]


def test_a_campaign_with_a_different_t_s_names_the_run(campaign_dir):
    directory = campaign_dir()
    bad = directory / "run_0003.h5"
    _rewrite(bad, "t_s", _values(bad, "t_s") * 1.1)  # still from 0, still increasing

    with pytest.raises(RunDataError, match=re.escape(f"{bad}: t_s differs")):
        load_campaign(directory)


def test_an_empty_campaign_directory_is_rejected(tmp_path):
    with pytest.raises(RunDataError, match=re.escape(f"{tmp_path}: no run_*.h5 files found")):
        load_campaign(tmp_path)


def test_the_readme_table_states_exactly_the_datasets_the_loader_reads():
    rows = re.findall(r"^\| `([^`]+)` \| `\(N,( 3)?\)` \| `([^`]+)` \|", README.read_text(), re.M)

    stated = {name: (units, 3 if width else None) for name, width, units in rows}
    assert stated == {name: (spec.units, spec.width) for name, spec in DATASETS.items()}
