"""The campaign check in `tests/conftest.py`, run by pytester in a tree laid out like this
repository's, with its pytest options, under a bare `pytest -n 2`: it reports a loaded campaign,
and fails naming a stale file, run files scattered over two directories, or a run the loader
rejects."""

import json
import textwrap
import tomllib
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

CONFTEST = Path(__file__).with_name("conftest.py")
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

# Two scenario cases writing run files into $CAMPAIGN; $SCATTER sends case 1 to a sibling
# directory, and $BAD_T_S gives case 1 a longer t_s.
STUB_SCENARIO = """
    import os
    from pathlib import Path

    import h5py
    import numpy as np
    import pytest
    from gnc_analysis.runs import DATASETS


    @pytest.mark.parametrize("case", [0, 1])
    def test_case(case, record_property):
        directory = Path(os.environ["CAMPAIGN"])
        if case == 1 and os.environ.get("SCATTER"):
            directory = directory.with_name("elsewhere")
        directory.mkdir(exist_ok=True)
        n = 5 + (case if os.environ.get("BAD_T_S") else 0)
        path = directory / f"run_{case:04d}.h5"
        with h5py.File(path, "w") as f:
            f.attrs["case"], f.attrs["seed"] = case, 0
            for name, spec in DATASETS.items():
                shape = (n,) if spec.width is None else (n, spec.width)
                data = np.arange(n, dtype=float) if name == "t_s" else np.zeros(shape)
                f.create_dataset(name, data=data).attrs["units"] = spec.units
        record_property("run_file", str(path))
"""


@pytest.fixture
def campaign(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Path:
    options = tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]
    pytester.makepyprojecttoml(
        "[tool.pytest.ini_options]\n"
        + "".join(f"{key} = {json.dumps(value)}\n" for key, value in options.items())
    )
    (pytester.path / "tests" / "sim").mkdir(parents=True)
    (pytester.path / "tests" / "conftest.py").write_text(CONFTEST.read_text())
    (pytester.path / "tests" / "sim" / "test_scenario.py").write_text(
        textwrap.dedent(STUB_SCENARIO)
    )
    directory = pytester.path / "campaign"
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("CAMPAIGN", str(directory))
    return directory


def _run(pytester: pytest.Pytester) -> pytest.RunResult:
    return pytester.runpytest_subprocess("-p", "xdist.plugin", "-n", "2")


def test_a_good_campaign_reports_its_runs(pytester, campaign):
    result = _run(pytester)

    assert result.ret == 0
    result.stdout.fnmatch_lines([f"campaign check: 2 runs loaded from {campaign}"])


def test_a_stale_run_file_fails_the_session_by_name(pytester, campaign):
    campaign.mkdir()
    (campaign / "run_0099.h5").write_bytes(b"")

    result = _run(pytester)

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["FAILED: present in * but written by no case: *run_0099.h5"])


def test_run_files_in_two_directories_fail_the_session(pytester, campaign, monkeypatch):
    monkeypatch.setenv("SCATTER", "1")

    result = _run(pytester)

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["FAILED: run files written to 2 directories: *"])


def test_a_campaign_the_loader_rejects_fails_the_session(pytester, campaign, monkeypatch):
    monkeypatch.setenv("BAD_T_S", "1")

    result = _run(pytester)

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["FAILED: *run_0001.h5: t_s differs*"])
