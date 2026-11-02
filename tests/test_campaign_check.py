"""The campaign check in `tests/conftest.py`, run by pytester in a tree laid out like this
repository's, with its pytest options, under a bare `pytest -n 2`: it reports a loaded campaign,
and fails naming a stale file or a run the loader rejects."""

import json
import textwrap
import tomllib
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

CONFTEST = Path(__file__).with_name("conftest.py")
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

# Stands in for WiseDynamics' plugin: the campaign directory is --sim-out.
STUB_PLUGIN = """
    from pathlib import Path
    from types import SimpleNamespace


    def pytest_addoption(parser):
        parser.addoption("--sim-out")


    def campaign_from_config(config):
        return SimpleNamespace(out_dir=Path(config.getoption("--sim-out")))
"""

# Two scenario cases, each writing a run file; case 1's t_s is longer when BAD_T_S is set.
STUB_SCENARIO = """
    import os
    from pathlib import Path

    import h5py
    import numpy as np
    import pytest
    from gnc_analysis.runs import DATASETS


    @pytest.mark.parametrize("case", [0, 1])
    def test_case(case, request, record_property):
        n = 5 + (case if os.environ.get("BAD_T_S") else 0)
        path = Path(request.config.getoption("--sim-out")) / f"run_{case:04d}.h5"
        with h5py.File(path, "w") as f:
            f.attrs["case"], f.attrs["seed"] = case, 0
            for name, spec in DATASETS.items():
                shape = (n,) if spec.width is None else (n, spec.width)
                data = np.arange(n, dtype=float) if name == "t_s" else np.zeros(shape)
                f.create_dataset(name, data=data).attrs["units"] = spec.units
        record_property("run_file", str(path))
"""


@pytest.fixture
def campaign_tree(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Path:
    options = tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]
    pytester.makepyprojecttoml(
        "[tool.pytest.ini_options]\n"
        + "".join(f"{key} = {json.dumps(value)}\n" for key, value in options.items())
    )
    (pytester.path / "wise_dynamics").mkdir()
    (pytester.path / "wise_dynamics" / "__init__.py").write_text("")
    (pytester.path / "wise_dynamics" / "pytest_plugin.py").write_text(textwrap.dedent(STUB_PLUGIN))
    (pytester.path / "tests" / "sim").mkdir(parents=True)
    (pytester.path / "tests" / "conftest.py").write_text(CONFTEST.read_text())
    (pytester.path / "tests" / "sim" / "test_scenario.py").write_text(
        textwrap.dedent(STUB_SCENARIO)
    )
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTHONPATH", str(pytester.path))
    out_dir = pytester.path / "campaign"
    out_dir.mkdir()
    return out_dir


def _run(pytester: pytest.Pytester, out_dir: Path) -> pytest.RunResult:
    return pytester.runpytest_subprocess(
        "-p", "xdist.plugin", "-p", "wise_dynamics.pytest_plugin", "-n", "2",
        f"--sim-out={out_dir}",
    )  # fmt: skip


def test_a_good_campaign_reports_its_runs(pytester, campaign_tree):
    result = _run(pytester, campaign_tree)

    assert result.ret == 0
    result.stdout.fnmatch_lines([f"campaign check: 2 runs loaded from {campaign_tree}"])


def test_a_stale_run_file_fails_the_session_by_name(pytester, campaign_tree):
    (campaign_tree / "run_0099.h5").write_bytes(b"")

    result = _run(pytester, campaign_tree)

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["FAILED: present in * but written by no case: *run_0099.h5"])


def test_a_campaign_the_loader_rejects_fails_the_session(pytester, campaign_tree, monkeypatch):
    monkeypatch.setenv("BAD_T_S", "1")

    result = _run(pytester, campaign_tree)

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["FAILED: *run_0001.h5: t_s differs*"])
