"""The generic partitions name no algorithm, and the deployment reaches algorithms only through FPP.

The names are read from the tree: each directory under `algorithms/`, each configuration, and the
component and instance name of each GNC instance of a component an algorithm defines, so F´'s own
components, such as a rate group, are not names. A name matches regardless of case; an instance
name matches only as a whole word, so `nav` is not found in `navigate`. The files are the tracked
ones, so a generated dictionary or extension beside them is not read, and each directory must
give at least one, so a renamed directory fails rather than passing over nothing. Test files,
`*_test.py` and `conftest.py`, are left out until #93 Framework tests range over the contract,
never nav or the IMU deletes the exclusion. The names are read from FPP, so the first grep skips
without the F´ framework clone, as the F´ tests skip without the F´ build.
"""

import re
import subprocess
from pathlib import Path

import pytest

from fsw.codegen.deployment import CLONE, algorithm_files, contract_files, gnc_instances
from fsw.codegen.fpp_model import read

_REPOSITORY = Path(__file__).resolve().parents[1]

GENERIC = (
    "fsw/fprime/cdh",
    "fsw/fprime/rio",
    "fsw/fprime/platform",
    "fsw/python/cdh",
    "fsw/python/rio",
    "fsw/python/platform",
    "lab",
)
"""The partitions every configuration shares, and the lab that hosts the F´ build."""

DEPLOYMENT = "fsw/fprime/deployment"
"""The templates rendering each configuration's deployment from its GNC sub-topology."""


def _tracked(*paths: str) -> list[Path]:
    """The files git tracks under the paths, test files included.

    Args:
        *paths: directories, relative to the repository.

    Returns:
        The files, relative to the repository.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", *paths],
        cwd=_REPOSITORY,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [Path(name) for name in listed.split("\0") if name]


def _scanned(*directories: str) -> list[Path]:
    """The tracked files under the directories that are not tests, at least one from each.

    Args:
        *directories: directories, relative to the repository.

    Returns:
        The files, relative to the repository.
    """
    files = []
    for directory in directories:
        found = [path for path in _tracked(directory) if not _is_test(path)]
        assert found, f"{directory} holds no tracked file to scan"
        files += found
    return files


def _algorithm_names() -> re.Pattern[str]:
    """Every name of an algorithm, as one case-insensitive pattern.

    Returns:
        The pattern: each algorithm directory, configuration and component as a substring, and
        each instance name as a whole word.
    """
    directories = {path.parts[1] for path in _tracked("algorithms") if len(path.parts) > 2}
    without_algorithms = tuple(f for f in contract_files() if f not in algorithm_files())
    algorithm_components = set(read(contract_files()).components) - set(
        read(without_algorithms).components
    )
    substrings, words = set(directories), set()
    for instance in gnc_instances():
        configuration, name = instance.name.split(".")
        substrings.add(configuration)
        if instance.component in algorithm_components:
            substrings.add(instance.component.split(".")[-1])
            words.add(name)
    alternatives = [re.escape(name) for name in sorted(substrings)]
    alternatives += [rf"\b{re.escape(name)}\b" for name in sorted(words)]
    return re.compile("|".join(alternatives), re.IGNORECASE)


def _is_test(path: Path) -> bool:
    """Whether a file is a test file, which the first grep leaves out.

    Args:
        path: the file.

    Returns:
        True for `*_test.py` and `conftest.py`.
    """
    return path.name.endswith("_test.py") or path.name == "conftest.py"


def test_no_generic_partition_or_lab_file_names_an_algorithm():
    """No tracked file but a test under a generic partition or `lab/` holds an algorithm's name."""
    if not CLONE.is_dir():
        pytest.skip("the F´ framework clone is absent; run `just pinned`")
    pattern = _algorithm_names()

    found = [
        f"{path}:{number}: {line.strip()}"
        for path in _scanned(*GENERIC)
        for number, line in enumerate((_REPOSITORY / path).read_text().splitlines(), 1)
        if pattern.search(line)
    ]

    assert not found, "an algorithm is named in a generic partition:\n" + "\n".join(found)


def test_the_deployment_reaches_no_algorithm_by_its_path():
    """No tracked file rendering a deployment names a path under `algorithms/`."""
    found = [
        f"{path}:{number}: {line.strip()}"
        for path in _scanned(DEPLOYMENT)
        for number, line in enumerate((_REPOSITORY / path).read_text().splitlines(), 1)
        if "algorithms/" in line
    ]

    assert not found, "a deployment template names an algorithm's path:\n" + "\n".join(found)
