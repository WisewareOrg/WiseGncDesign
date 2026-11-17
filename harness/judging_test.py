"""The judge: cells, verdicts and the evidence they write, from a session and a requirements tree.

The tests write a requirements tree and a session in a pytester project, copy in the three real
analyzers and judge it. Each rung has p = 0.8, c = 0.5 and x = 1e-3 in its units; of 10 planned
cases that allows one failure, as `allowed_failures(10, 0.8, 0.5)` gives. SRS901 is the attitude
rung, SRS902 the velocity rung and SRS903 the position rung, all under the capability SYS901 and
all linked by the scenario TST901.
"""

import json
import math
import re
from collections.abc import Callable
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml
from wise_dynamics.sessions import crash_path, run_path, write_planned

from harness import notebook, requirements_tree

REPO = Path(__file__).resolve().parents[1]
GOOD = 0.9e-3
BAD = 1.5e-3
PLANNED = 10
KINDS = {"attitude": "SRS901", "velocity": "SRS902", "position": "SRS903"}

NODE = "missions/nb/Test_vehicle/test_fsw_alpha"
NODEID = "missions/nb.py::Test_vehicle::test_fsw_alpha"
ALL = {"scenario": "TST901", "capabilities": ["SYS901"], "rungs": None}


def write_item(root: Path, document: str, uid: str, **fields: object) -> None:
    """Write one item of the tree.

    Args:
        root: the project root.
        document: "sys", "srs" or "tst".
        uid: the item's ID.
        **fields: the item's fields beyond `active`.
    """
    folder = root / "docs" / "requirements" / document
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{uid}.yml").write_text(yaml.safe_dump({"active": True, "header": uid, **fields}))


def write_tree(root: Path) -> None:
    """Write the tree: one capability, the three rungs, one scenario linking them.

    Args:
        root: the project root.
    """
    write_item(root, "sys", "SYS901", links=[])
    for name, uid in KINDS.items():
        write_item(
            root,
            "srs",
            uid,
            links=[{"SYS901": "stamp"}],
            references=[
                {
                    "path": f"analysis/test_{name}_knowledge.py",
                    "keyword": f"def test_{name}_knowledge(",
                    "type": "file",
                }
            ],
            x=float(np.rad2deg(1e-3)) if name == "attitude" else 1e-3,
            p=0.8,
            c=0.5,
        )
    write_item(root, "tst", "TST901", links=[{uid: "stamp"} for uid in KINDS.values()])


def write_run(path: Path, error: float, kind: str = "attitude") -> None:
    """Write a run whose worst `kind` error is `error`, with no error of the other kinds.

    Args:
        path: the run file to create.
        error: the estimate's error at one sample, in rad, m/s or m.
        kind: "attitude", "velocity" or "position".
    """
    identity = np.tile([1.0, 0.0, 0.0, 0.0], (5, 1))
    tlm = {
        "nav.bodyEciAttitude": identity.copy(),
        "nav.bodyEciVel": np.zeros((5, 3)),
        "nav.bodyEciPos": np.zeros((5, 3)),
    }
    if kind == "attitude":
        tlm["nav.bodyEciAttitude"][2] = [np.cos(error / 2.0), 0.0, 0.0, np.sin(error / 2.0)]
    else:
        tlm["nav.bodyEciVel" if kind == "velocity" else "nav.bodyEciPos"][2, 0] = error
    t_s = np.linspace(0.0, 1.0, 5)
    with h5py.File(path, "w") as f:
        f["t_s"] = t_s
        f["truth/q_BN"] = identity
        for truth in ("v_N", "r_N"):
            f[f"truth/{truth}"] = np.zeros((5, 3))
        for name, values in tlm.items():
            f[f"tlm/{name}"] = values
            f[f"tlm_t/{name}"] = t_s


def write_cases(
    session: Path,
    bad: tuple[int, ...] = (),
    crashed: tuple[int, ...] = (),
    missing: tuple[int, ...] = (),
    nan: tuple[int, ...] = (),
    kind: str = "attitude",
    planned: int = PLANNED,
    node: str = NODE,
    nodeid: str = NODEID,
    flight: dict | None = ALL,
) -> Path:
    """Write a test's folder in a session, as a campaign leaves it.

    Args:
        session: the session's directory.
        bad: cases whose run exceeds the threshold.
        crashed: cases with a crash record and no run file.
        missing: cases with neither file.
        nan: cases whose error is NaN.
        kind: the error the runs carry, as `write_run` takes it.
        planned: the planned case count.
        node: the folder, relative to the session.
        nodeid: the node ID recorded in the folder.
        flight: the folder's `flight.json`, or None for none.

    Returns:
        The folder.
    """
    directory = session / node
    write_planned(directory, planned, nodeid)
    if flight is not None:
        (directory / "flight.json").write_text(json.dumps(flight))
    for case in range(planned):
        if case in missing:
            continue
        if case in crashed:
            crash_path(directory, case).write_text(json.dumps({"exception": "boom"}))
        else:
            error = math.nan if case in nan else BAD if case in bad else GOOD
            write_run(run_path(directory, case), error, kind)
    return directory


def only(rung: str) -> dict:
    """A flight judged on one rung of the capability.

    Args:
        rung: the SRS ID.

    Returns:
        The `flight.json` content.
    """
    return {"scenario": "TST901", "capabilities": ["SYS901"], "rungs": [rung]}


@pytest.fixture
def project(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A project with the tree, the analyzers, an unimportable notebook and a session.

    The notebook, `missions/nb.py`, records that it was imported and then raises.

    Args:
        pytester: the pytester fixture.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The pytester, rooted in the project.
    """
    monkeypatch.delenv("WISE_DYNAMICS_CAPPED", raising=False)
    monkeypatch.setenv("COLUMNS", "400")
    pytester.makefile(".ini", pytest="[pytest]\n")
    files = {"analysis/conftest": "from harness.judging import *  # noqa: F403\n"}
    for name in KINDS:
        files[f"analysis/test_{name}_knowledge"] = (
            REPO / "analysis" / f"test_{name}_knowledge.py"
        ).read_text()
    files["missions/nb"] = (
        f'from pathlib import Path\nPath(r"{pytester.path}/imported").write_text("")\n'
        'raise RuntimeError("the notebook was imported")\n'
    )
    pytester.makepyfile(**files)
    write_tree(pytester.path)
    (pytester.path / "monte_carlo").mkdir()
    (pytester.path / "monte_carlo" / "SESSION").write_text("s1\n")
    return pytester


def session(project: pytest.Pytester, name: str = "s1") -> Path:
    """A session's directory in the project.

    Args:
        project: the project.
        name: the session.

    Returns:
        The directory.
    """
    return project.path / "monte_carlo" / name


def judge(project: pytest.Pytester, *args: str) -> pytest.RunResult:
    """Judge the project's analyzers in a subprocess.

    Args:
        project: the project.
        *args: more pytest arguments.

    Returns:
        The result.
    """
    return project.runpytest_subprocess("analysis", "-rs", "-p", "no:xdist", *args)


def cell_matrix(project: pytest.Pytester, name: str = "s1") -> str:
    """The matrix the judge wrote for the test `NODE`.

    Args:
        project: the project.
        name: the session.

    Returns:
        Its text.
    """
    return (session(project, name) / "report" / NODE / "matrix.md").read_text()


def test_allowed_failures_matches_the_known_values(project: pytest.Pytester) -> None:
    """The rule reproduces the proposal's table, including the no-such-k case as None.

    Args:
        project: the project.
    """
    project.makepyfile(
        **{
            "analysis/test_rule": """\
import pytest


@pytest.mark.parametrize(
    ("n", "p", "c", "expected"),
    [(852, 0.99, 0.90, 4), (852, 0.9973, 0.90, 0), (851, 0.9973, 0.90, None)],
)
def test_rule(allowed_failures, n, p, c, expected):
    assert allowed_failures(n, p, c) == expected
"""
        }
    )

    project.runpytest_subprocess("analysis/test_rule.py", "-p", "no:xdist").assert_outcomes(
        passed=3
    )


@pytest.mark.parametrize(
    ("cases", "outcomes", "lines", "cell", "rollup"),
    [
        pytest.param(
            {"bad": (3,), "flight": only("SRS901")},
            {"passed": 1, "skipped": 2},
            [],
            "| SRS901 | pass | 1/10/10 | 1 | 3 |",
            None,
            id="within-allowance",
        ),
        pytest.param(
            {"bad": (3,), "crashed": (5,), "flight": only("SRS901")},
            {"failed": 1, "skipped": 2},
            [f"*{NODEID}: 2 failed, 1 allowed*"],
            "| SRS901 | fail | 2/10/10 | 1 | 3, 5 (crash) |",
            None,
            id="crash",
        ),
        pytest.param(
            {"bad": (2, 7), "flight": only("SRS901")},
            {"failed": 1, "skipped": 2},
            [
                f'*case 2: uv run --no-sync pytest "{NODEID}[[]2[]]"*--full-monte-carlo*',
                f'*case 7: uv run --no-sync pytest "{NODEID}[[]7[]]"*--full-monte-carlo*',
            ],
            "| SRS901 | fail | 2/10/10 | 1 | 2, 7 |\n",
            f"| SRS901 | [fail, 2 of 1 allowed]({NODE}/SRS901.png) | fail |",
            id="over-allowance",
        ),
        pytest.param(
            {"crashed": tuple(range(PLANNED)), "flight": only("SRS901")},
            {"failed": 1, "skipped": 2},
            [],
            "| SRS901 | fail | 10/10/10 | 1 |",
            None,
            id="all-crashed",
        ),
        pytest.param(
            {"missing": (4,), "planned": 5, "flight": only("SRS901")},
            {"passed": 1, "skipped": 2},
            [],
            "| SRS901 | pass | 0/4/5 | 0 |",
            None,
            id="missing-case",
        ),
        pytest.param(
            {"bad": (2, 7), "kind": "velocity", "flight": only(KINDS["velocity"])},
            {"failed": 1, "skipped": 2},
            [f"*{NODEID}: 2 failed, 1 allowed*"],
            None,
            None,
            id="velocity",
        ),
        pytest.param(
            {"bad": (2, 7), "kind": "position", "flight": only(KINDS["position"])},
            {"failed": 1, "skipped": 2},
            [f"*{NODEID}: 2 failed, 1 allowed*"],
            None,
            None,
            id="position",
        ),
        pytest.param(
            {"bad": (2,), "nan": (5,), "kind": "velocity", "flight": only("SRS902")},
            {"failed": 1, "skipped": 2},
            [],
            "| SRS902 | fail | 2/10/10 | 1 | 2, 5 |",
            None,
            id="nan",
        ),
    ],
)
def test_a_rung_is_judged_on_the_runs_found(
    project: pytest.Pytester,
    cases: dict,
    outcomes: dict,
    lines: list[str],
    cell: str | None,
    rollup: str | None,
) -> None:
    """A rung passes within its allowance of failures, and fails over it, on the runs found.

    One failure of ten is allowed. A crash, and a NaN error, count as failed cases; ten crashes
    are ten failed cases, counted as found. A failing rung names a rerun command per failing case,
    each carrying `--full-monte-carlo`. An interrupted campaign is judged on the runs found: n
    counts runs and crash records only, so four of five planned cases within x show p = 0.8 at
    c = 0.5. The velocity and position analyzers read their own datasets. Nothing is skipped.

    Args:
        project: the project.
        cases: the folder's cases, as `write_cases` takes them.
        outcomes: the judge's outcomes.
        lines: lines the judge prints, as `fnmatch_lines` takes them, or none.
        cell: a row of the test's matrix, or None.
        rollup: a row of the session's matrix, or None.
    """
    write_cases(session(project), **cases)

    result = judge(project)

    result.assert_outcomes(**outcomes)
    result.stdout.fnmatch_lines(lines)
    if cell is not None:
        assert cell in cell_matrix(project)
    matrix = (session(project) / "report" / "matrix.md").read_text()
    if rollup is not None:
        assert rollup in matrix
    assert "## Skipped folders" not in matrix


def test_too_few_cases_found_leave_the_rung_not_judged(project: pytest.Pytester) -> None:
    """Three runs found cannot show p = 0.8 at c = 0.5 even with no failure, whatever was planned.

    Args:
        project: the project.
    """
    write_cases(session(project), missing=(3, 4), planned=5, flight=only("SRS901"))

    result = judge(project)

    result.assert_outcomes(skipped=3)
    result.stdout.fnmatch_lines(["*test_fsw_alpha: 3 cases cannot show p=0.8 at c=0.5*"])


def test_a_flight_judges_only_the_rungs_its_filter_names(project: pytest.Pytester) -> None:
    """A flight filtered to the velocity rung gives no cell to the attitude rung, whose runs fail.

    Args:
        project: the project.
    """
    write_cases(session(project), bad=(1, 2, 3), flight=only("SRS902"))

    result = judge(project)

    result.assert_outcomes(passed=1, skipped=2)
    result.stdout.fnmatch_lines(["*SRS901 not judged: no test claims it*"])
    matrix = cell_matrix(project)
    assert "| SRS902 | pass |" in matrix
    assert "SRS901" not in matrix


def test_rungs_judged_on_separate_workers_share_the_matrix(project: pytest.Pytester) -> None:
    """Each analyzer's cells reach `matrix.md` when xdist spreads the analyzers over workers.

    Args:
        project: the project.
    """
    write_cases(session(project))

    project.runpytest_subprocess("analysis", "-n", "3").assert_outcomes(passed=3)

    matrix = (session(project) / "report" / "matrix.md").read_text()
    assert [row.split(" | ")[0] for row in matrix.splitlines()[2:5]] == [
        "| SRS901",
        "| SRS902",
        "| SRS903",
    ]


def test_a_stale_report_is_removed_before_judging(project: pytest.Pytester) -> None:
    """A cell from an earlier judging does not survive into this one's matrices.

    Args:
        project: the project.
    """
    stale = session(project) / "report" / "missions" / "old" / "Test_vehicle" / "test_old"
    stale.mkdir(parents=True)
    (stale / "SRS901.json").write_text(
        json.dumps(
            {
                "requirement": "SRS901",
                "verdict": "fail",
                "failed": 9,
                "found": 10,
                "planned": 10,
                "allowed": 1,
                "failed_cases": "1",
            }
        )
    )
    write_cases(session(project), flight=only("SRS901"))

    judge(project).assert_outcomes(passed=1, skipped=2)

    assert not stale.exists()
    assert "test_old" not in (session(project) / "report" / "matrix.md").read_text()


def test_a_notebook_that_raises_on_import_is_still_judged(project: pytest.Pytester) -> None:
    """The judge reads the flight's facts from its folder and never imports the notebook.

    Args:
        project: the project.
    """
    write_cases(session(project), flight=only("SRS901"))

    judge(project).assert_outcomes(passed=1, skipped=2)

    assert not (project.path / "imported").exists()


def test_folders_without_a_flight_or_a_test_file_are_skipped_and_listed(
    project: pytest.Pytester,
) -> None:
    """The rest are judged; each skipped folder is listed under "Skipped folders" with its reason.

    Args:
        project: the project.
    """
    root = session(project)
    write_cases(root, flight=only("SRS901"))
    write_cases(
        root,
        node="missions/nb/Test_vehicle/test_unflown",
        nodeid="missions/nb.py::Test_vehicle::test_unflown",
        flight=None,
    )
    write_cases(
        root,
        node="missions/gone/Test_vehicle/test_fsw_beta",
        nodeid="missions/gone.py::Test_vehicle::test_fsw_beta",
        flight=only("SRS901"),
    )

    judge(project).assert_outcomes(passed=1, skipped=2)

    matrix = (root / "report" / "matrix.md").read_text()
    head, heading, listing = matrix.partition("## Skipped folders")
    assert "| SRS901 |" in head
    assert heading
    assert sorted(line for line in listing.splitlines() if line.strip()) == [
        "- missions/gone/Test_vehicle/test_fsw_beta: test file gone",
        "- missions/nb/Test_vehicle/test_unflown: no flight.json",
    ]


def test_capped_runs_are_judged_in_scratch_and_leave_the_active_session_alone(
    project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the capped variable set the judge reads `scratch`, not the session the pointer names.

    Args:
        project: the project.
        monkeypatch: the monkeypatch fixture.
    """
    monkeypatch.setenv("WISE_DYNAMICS_CAPPED", "1")
    item = project.path / "docs" / "requirements" / "srs" / "SRS901.yml"
    fields = yaml.safe_load(item.read_text()) | {"p": 0.5, "c": 0.5}
    item.write_text(yaml.safe_dump(fields))
    write_cases(session(project, "scratch"), bad=(1,), planned=2, flight=only("SRS901"))
    kept = session(project) / "report"
    kept.mkdir(parents=True)
    (kept / "matrix.md").write_text("the active session's rollup\n")

    judge(project).assert_outcomes(failed=1, skipped=2)

    assert "| SRS901 | " in cell_matrix(project, "scratch")
    assert (kept / "matrix.md").read_text() == "the active session's rollup\n"
    assert [path.name for path in kept.iterdir()] == ["matrix.md"]


def test_the_notebook_judge_returns_the_matrix_lists_skipped_folders_and_plots_the_rung(
    project: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The notebook's `judge()` returns the matrix and prints what it skipped; `plots()` shows PNGs.

    The matrix has a row per rung and a column per flight; `plots()` shows the rung's PNG for each
    flight.

    Args:
        project: the project.
        monkeypatch: the monkeypatch fixture.
        capsys: the capture fixture.
    """
    root = session(project)
    write_cases(root, bad=(3,), flight=only("SRS901"))
    write_cases(
        root,
        node="missions/nb/Test_vehicle/test_unflown",
        nodeid="missions/nb.py::Test_vehicle::test_unflown",
        flight=None,
    )
    monkeypatch.chdir(project.path)
    monkeypatch.setattr(requirements_tree, "ROOT", project.path)
    shown = []
    monkeypatch.setattr(notebook, "display", shown.append)

    matrix = notebook.judge()

    assert matrix.to_dict() == {"nb: vehicle / fsw_alpha": {"SRS901 SRS901": "pass 1/1"}}
    printed = capsys.readouterr().out
    assert "SRS902 not judged: no test claims it" in printed
    assert "Skipped folders:\n- missions/nb/Test_vehicle/test_unflown: no flight.json" in printed

    notebook.plots("SRS901")

    [image] = shown
    assert Path(image.filename) == root / "report" / NODE / "SRS901.png"
    assert Path(image.filename).read_bytes().startswith(b"\x89PNG")
    assert "nb/Test_vehicle/test_fsw_alpha" in capsys.readouterr().out


def test_a_flown_mission_is_judged_end_to_end(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """A mission flown through the real plugin leaves a session the real judge reads.

    The flight's `flight.json` and run files come from the simulator's own writers, so a key or
    dataset the writer and the judge disagree on makes this fail. Four cases are the fewest that
    show p = 0.8 at c = 0.5. The flight software is `MockFlight` of `fsw.mock.MOCK`, writing
    the nav role's estimate channels with a fixed state, and each rung's x is set far above its
    error so the verdict rests on the agreement alone.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    root = project.path
    for uid in KINDS.values():
        item = root / "docs" / "requirements" / "srs" / f"{uid}.yml"
        item.write_text(yaml.safe_dump(yaml.safe_load(item.read_text()) | {"x": 1e9}))
    write_item(
        root,
        "tst",
        "TST901",
        links=[{uid: "stamp"} for uid in KINDS.values()],
        references=[{"path": "scenarios/alpha.py", "keyword": "def alpha(", "type": "file"}],
    )
    project.mkdir("scenarios")
    (root / "scenarios" / "alpha.py").write_text(
        "import pytest\n\n\n"
        '@pytest.mark.sim_scenario("leo500")\n'
        "@pytest.mark.sim_duration_s(2.0)\n"
        "@pytest.mark.sim_runs(4)\n"
        "async def alpha(ground) -> None:\n"
        "    pass\n"
    )
    project.makepyfile(
        test_flights="""
from fsw.mock import MOCK
from harness.mission import Mission, mission_tests

globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="MockFlight", build="python", scenarios=("TST901",),
            contract=MOCK,
        )
    )
)
"""
    )

    fly_in_a_subprocess(project, "test_flights.py", "--full-monte-carlo").assert_outcomes(passed=4)
    node = "test_flights/Test_imu_spacecraft/test_MockFlight_python_alpha"
    flown = session(project) / node
    assert sorted(path.name for path in flown.glob("run_*.h5")) == [
        f"run_000{case}.h5" for case in range(4)
    ]

    judge(project).assert_outcomes(passed=3)

    matrix = (session(project) / "report" / node / "matrix.md").read_text()
    for uid in KINDS.values():
        assert f"| {uid} | pass | 0/4/4 | 0 |" in matrix
        assert (
            (session(project) / "report" / node / f"{uid}.png").read_bytes().startswith(b"\x89PNG")
        )


def test_the_notebook_judge_raises_when_the_analysis_run_itself_fails(
    project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An analyzer that cannot be collected is an error, not a stale or empty matrix.

    Args:
        project: the project.
        monkeypatch: the monkeypatch fixture.
    """
    write_cases(session(project), flight=only("SRS901"))
    (project.path / "analysis" / "test_attitude_knowledge.py").write_text("def broken(:\n")
    monkeypatch.chdir(project.path)
    monkeypatch.setattr(requirements_tree, "ROOT", project.path)

    with pytest.raises(RuntimeError, match=r"judging failed \(2\)"):
        notebook.judge()


def test_the_notebook_judge_reports_a_failed_rung_in_its_matrix(
    project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rung the flight's cases fail is a `fail` verdict in the matrix, not an error.

    Args:
        project: the project.
        monkeypatch: the monkeypatch fixture.
    """
    write_cases(session(project), bad=(1, 2, 3), flight=only("SRS901"))
    monkeypatch.chdir(project.path)
    monkeypatch.setattr(requirements_tree, "ROOT", project.path)

    matrix = notebook.judge()

    assert matrix.to_dict() == {"nb: vehicle / fsw_alpha": {"SRS901 SRS901": "fail 3/1"}}


@pytest.mark.parametrize(
    "edit",
    [
        ("tlm_t/nav.bodyEciAttitude", "tlm_t/nav.noSuchChannel"),
        (
            "    verdict: Callable[..., None],\n",
            "    verdict: Callable[..., None],\n    no_such_fixture: None,\n",
        ),
    ],
    ids=["crash-in-the-call", "error-in-setup"],
)
def test_the_notebook_judge_raises_naming_an_analyzer_that_errors(
    project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, edit: tuple[str, str]
) -> None:
    """An analyzer that errors, in its call or its setup, raises, naming its test by node ID.

    The error carries the analyzers' run's output, its summary among it.

    The flight's cases fail SRS901, so only the analyzer's own error tells the two apart.

    Args:
        project: the project.
        monkeypatch: the monkeypatch fixture.
        edit: `(old, new)` applied to the attitude analyzer: a channel the run lacks, or a fixture
            nothing defines.
    """
    write_cases(session(project), bad=(1, 2, 3), flight=only("SRS901"))
    analyzer = project.path / "analysis" / "test_attitude_knowledge.py"
    text = analyzer.read_text()
    assert edit[0] in text
    analyzer.write_text(text.replace(*edit))
    monkeypatch.chdir(project.path)
    monkeypatch.setattr(requirements_tree, "ROOT", project.path)

    test = re.escape("analysis/test_attitude_knowledge.py::test_attitude_knowledge[SRS901]")
    with pytest.raises(RuntimeError, match=rf"errored rather than judging:\n- {test}: ") as raised:
        notebook.judge()

    assert "short test summary info" in str(raised.value)
