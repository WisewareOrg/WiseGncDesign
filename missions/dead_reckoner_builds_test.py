"""The dead reckoner's two builds are deterministic and agree, flown through the same mission.

Each flight runs in a pytest subprocess writing under a temporary output root, so it shares no
process with this test and leaves `monte_carlo/` alone.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

pytestmark = pytest.mark.xdist_group("dead_reckoner_builds")

MISSION = Path(__file__).with_name("dead_reckoner_python_vs_fprime.py")
PYTHON, FPRIME = "test_dead_reckoner_leo500", "test_fprime_dead_reckoner_leo500"
FPRIME_BUILT = importlib.util.find_spec("gnc_cdh.fprime._wise_fsw") is not None
BUILDS = [PYTHON, FPRIME] if FPRIME_BUILT else [PYTHON]
TOLERANCE = 1e-12
"""Position and velocity relative to the vector's norm, attitude in rad."""


def _fly(out: Path, *tests: str) -> Path:
    """Flies the named tests of the mission, capped, in one fresh process.

    A case that fails its gross check has written its run file, which is what these tests compare,
    so only a run that pytest could not finish fails here.

    Args:
        out: the output root the flights write under.
        *tests: test names, each optionally with its case, such as `test_x[1]`.

    Returns:
        The directory holding one directory of run files per test.
    """
    nodes = [f"{MISSION}::Test_imu_spacecraft::{test}" for test in tests]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-n", "0", "-q", "-p", "no:cacheprovider"]
        + ["-o", f"sim_out={out}", *nodes],
        cwd=MISSION.parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED), (
        result.stdout + result.stderr
    )
    return out / "scratch" / "missions" / MISSION.stem / "Test_imu_spacecraft"


def _read(path: Path) -> tuple[dict[str, tuple[np.ndarray, str]], str]:
    """A run file's datasets with their units, and its command log.

    Args:
        path: the run file.

    Returns:
        Each dataset's path to its values, strings read as `str`, and units; and the command log
        as written.
    """
    datasets: dict[str, tuple[np.ndarray, str]] = {}

    def keep(name: str, node: h5py.HLObject) -> None:
        """Keeps a dataset with its units.

        Args:
            name: the node's path.
            node: the node.
        """
        if isinstance(node, h5py.Dataset):
            strings = h5py.check_string_dtype(node.dtype) is not None
            datasets[name] = ((node.asstr() if strings else node)[()], node.attrs["units"])

    with h5py.File(path, "r") as run:
        run.visititems(keep)
        return datasets, str(run.attrs["commands"])


@pytest.fixture(scope="module")
def after_case_0(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Cases 0 and 1 of each build, flown in one process.

    Args:
        tmp_path_factory: makes the output root.

    Returns:
        The directory holding each build's run files.
    """
    return _fly(tmp_path_factory.mktemp("after"), *BUILDS)


@pytest.mark.parametrize("build", BUILDS)
def test_a_case_flies_the_same_alone_and_after_another(
    build: str, after_case_0: Path, tmp_path: Path
):
    """Case 1 alone and case 1 after case 0 in one process write identical run files.

    Args:
        build: the build's test name.
        after_case_0: the flights of both cases in one process.
        tmp_path: the output root of the flight alone.
    """
    alone, alone_commands = _read(_fly(tmp_path, f"{build}[1]") / build / "run_0001.h5")
    after, after_commands = _read(after_case_0 / build / "run_0001.h5")

    assert sorted(alone) == sorted(after)
    for name, (values, units) in alone.items():
        np.testing.assert_array_equal(values, after[name][0], err_msg=name)
        assert units == after[name][1], name
    assert alone_commands == after_commands


@pytest.mark.skipif(not FPRIME_BUILT, reason="the F´ build is absent; run `just fsw`")
@pytest.mark.parametrize("case", ["run_0000.h5", "run_0001.h5"])
def test_the_python_and_fprime_builds_write_the_same_run_file(case: str, after_case_0: Path):
    """Case for case, the builds write the same datasets, units, write times and commands.

    Every dataset is equal but the estimate's values, which agree to `TOLERANCE`: position and
    velocity relative to the vector's norm, attitude as the principal angle between them.

    Args:
        case: the case's run file.
        after_case_0: the flights of both builds.
    """
    python, python_commands = _read(after_case_0 / PYTHON / case)
    fprime, fprime_commands = _read(after_case_0 / FPRIME / case)
    estimate = ("tlm/nav.bodyEciPos", "tlm/nav.bodyEciVel", "tlm/nav.bodyEciAttitude")

    assert sorted(python) == sorted(fprime)
    assert set(estimate) <= set(python)
    for name, (values, units) in python.items():
        assert values.dtype == fprime[name][0].dtype, name
        assert units == fprime[name][1], name
        if name not in estimate:
            np.testing.assert_array_equal(values, fprime[name][0], err_msg=name)
    for name in estimate[:2]:
        p, f = python[name][0], fprime[name][0]
        assert p.shape == f.shape, name
        assert np.max(np.linalg.norm(p - f, axis=1) / np.linalg.norm(p, axis=1)) <= TOLERANCE, name
    p, f = (
        Rotation.from_quat(run["tlm/nav.bodyEciAttitude"][0], scalar_first=True)
        for run in (python, fprime)
    )
    assert np.max((p * f.inv()).magnitude()) <= TOLERANCE
    assert python_commands == fprime_commands
