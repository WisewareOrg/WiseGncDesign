"""Missions: what a flight judges, what a mission refuses, and the record a flight leaves.

Every test reads a requirements tree it writes in `tmp_path`, by pointing the tree root at it, so
none depends on the repository's own tree. The tree holds two capabilities, four rungs and two
scenarios:

    SYS901 <- SRS901, SRS902, SRS904      SYS902 <- SRS903
    TST901 links SRS901, SRS902, SRS903   TST902 links SRS902
"""

import json
import os
import tomllib
from collections.abc import Callable
from pathlib import Path

import h5py
import pytest
import yaml

from harness import requirements_tree
from harness.mission import Mission, mission_tests, provides

VEHICLE = "imu_spacecraft"
ALPHA = """\
import pytest


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s({duration})
@pytest.mark.sim_runs(1)
async def alpha(ground) -> None:
    {body}
"""


def _write_item(
    root: Path, document: str, uid: str, links: list[str], reference: tuple[str, str] | None = None
) -> None:
    """Write one item of the tree.

    Args:
        root: the project root holding `docs/requirements`.
        document: "sys", "srs" or "tst".
        uid: the item's ID.
        links: the IDs it links to.
        reference: the `(path, keyword)` of the file the item references, if any.
    """
    item = {"active": True, "links": [{link: "stamp"} for link in links], "header": uid}
    if reference:
        item["references"] = [{"path": reference[0], "keyword": reference[1], "type": "file"}]
    folder = root / "docs" / "requirements" / document
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{uid}.yml").write_text(yaml.safe_dump(item))


def write_tree(root: Path, alpha_path: str = "scenarios/alpha.py") -> None:
    """Write the tree the module docstring draws.

    Args:
        root: the project root.
        alpha_path: the file TST901 references for its definition `alpha`.
    """
    for uid in ("SYS901", "SYS902"):
        _write_item(root, "sys", uid, [])
    for uid, parent in (
        ("SRS901", "SYS901"),
        ("SRS902", "SYS901"),
        ("SRS903", "SYS902"),
        ("SRS904", "SYS901"),
    ):
        _write_item(root, "srs", uid, [parent])
    _write_item(root, "tst", "TST901", ["SRS901", "SRS902", "SRS903"], (alpha_path, "def alpha("))
    _write_item(root, "tst", "TST902", ["SRS902"], ("scenarios/beta.py", "def beta("))


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tree in `tmp_path`, which the requirements tree functions read by default.

    Args:
        tmp_path: the test's directory.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The project root holding it.
    """
    write_tree(tmp_path)
    monkeypatch.setattr(requirements_tree, "ROOT", tmp_path)
    return tmp_path


def claiming(*capabilities: str, name: str = "build"):
    """A fresh FSW builder claiming capabilities.

    Args:
        *capabilities: the SYS IDs it claims.
        name: its function name.

    Returns:
        The builder.
    """

    def fsw(scenario: object) -> None:
        """Build nothing.

        Args:
            scenario: unused.
        """

    fsw.__name__ = name
    return provides(*capabilities)(fsw)


def test_the_tree_functions_read_the_default_root_when_called(tree: Path) -> None:
    """`items` reads the tree at the root the module holds now, not the one it held on import.

    Args:
        tree: the tree and its root.
    """
    assert sorted(requirements_tree.items("SYS")) == ["SYS901", "SYS902"]


def test_the_tree_functions_follow_the_root_when_it_is_reassigned(
    tree: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reassigning the module's `ROOT` points the tree functions at another project.

    Args:
        tree: the tree the default reads.
        tmp_path_factory: makes a second project.
        monkeypatch: the monkeypatch fixture.
    """
    other = tmp_path_factory.mktemp("other")
    _write_item(other, "sys", "SYS777", [])
    monkeypatch.setattr(requirements_tree, "ROOT", other)

    assert sorted(requirements_tree.items("SYS")) == ["SYS777"]


def test_a_flight_judges_the_scenarios_rungs_under_the_capabilities_claimed(tree: Path) -> None:
    """TST901 links SRS901-3; the capability SYS901 owns SRS901 and SRS902 only.

    Args:
        tree: the tree.
    """
    assert requirements_tree.flight_rungs("TST901", ["SYS901"]) == ("SRS901", "SRS902")
    assert requirements_tree.flight_rungs("TST901", ["SYS902"]) == ("SRS903",)
    assert requirements_tree.flight_rungs("TST901", ["SYS902", "SYS901"]) == (
        "SRS901",
        "SRS902",
        "SRS903",
    )


def test_the_filter_narrows_a_flights_rungs(tree: Path) -> None:
    """Only the filter's rungs that the scenario links and the capabilities own remain.

    Args:
        tree: the tree.
    """
    assert requirements_tree.flight_rungs("TST901", ["SYS901"], ["SRS902", "SRS903", "SRS904"]) == (
        "SRS902",
    )


def test_flight_rungs_reads_the_root_it_holds_when_called(
    tree: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tree is read from the module's `ROOT` as it stands at the call.

    Args:
        tree: the tree the default reads.
        tmp_path_factory: makes a second project.
        monkeypatch: the monkeypatch fixture.
    """
    other = tmp_path_factory.mktemp("other")
    write_tree(other)
    (other / "docs" / "requirements" / "tst" / "TST901.yml").write_text(
        yaml.safe_dump({"active": True, "links": [{"SRS904": "stamp"}]})
    )

    assert requirements_tree.flight_rungs("TST901", ["SYS901"]) == ("SRS901", "SRS902")
    monkeypatch.setattr(requirements_tree, "ROOT", other)
    assert requirements_tree.flight_rungs("TST901", ["SYS901"]) == ("SRS904",)


def test_a_mission_has_no_rung_filter_by_default(tree: Path) -> None:
    """`rungs` defaults to None, meaning every rung the flight reaches.

    Args:
        tree: the tree.
    """
    mission = Mission(VEHICLE, claiming("SYS901"), ("TST901",))

    assert mission.rungs is None


def test_a_filter_rung_outside_the_scenarios_is_refused(tree: Path) -> None:
    """SRS904 is under SYS901 but no scenario of the mission links it.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="SRS904"):
        Mission(VEHICLE, claiming("SYS901"), ("TST901",), rungs=("SRS904",))


def test_a_flight_with_no_rungs_is_refused(tree: Path) -> None:
    """An FSW claiming SYS902 judges nothing in TST902, which links only SRS902 under SYS901.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="TST902"):
        Mission(VEHICLE, claiming("SYS902"), ("TST902",))


def test_a_filter_that_empties_one_scenarios_flight_is_refused_naming_it(tree: Path) -> None:
    """SRS901 is linked by TST901 only, so the filter leaves TST902 with no rung to judge.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="TST902"):
        Mission(VEHICLE, claiming("SYS901"), ("TST901", "TST902"), rungs=("SRS901",))


def test_a_filter_answered_by_every_scenarios_flight_is_accepted(tree: Path) -> None:
    """SRS902 is linked by both TST901 and TST902, so each flight keeps a rung under the filter.

    Args:
        tree: the tree.
    """
    mission = Mission(VEHICLE, claiming("SYS901"), ("TST901", "TST902"), rungs=("SRS902",))

    assert mission.rungs == ("SRS902",)


def test_an_fsw_claiming_nothing_one_scenario_links_is_refused_naming_it(tree: Path) -> None:
    """SYS902 owns SRS903, which TST901 links but TST902 does not.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="TST902"):
        Mission(VEHICLE, claiming("SYS902"), ("TST901", "TST902"))


@pytest.mark.parametrize(
    ("changes", "unknown"),
    [
        ({"scenarios": ("TST999",)}, "TST999"),
        ({"rungs": ("SRS999",)}, "SRS999"),
        ({"vehicle": "no_such_vehicle"}, "no_such_vehicle"),
    ],
)
def test_unknown_names_are_refused(tree: Path, changes: dict, unknown: str) -> None:
    """A scenario, rung or vehicle that does not exist is a ValueError naming it.

    Args:
        tree: the tree.
        changes: the field replaced.
        unknown: the name it holds.
    """
    fields = {"vehicle": VEHICLE, "fsw": claiming("SYS901"), "scenarios": ("TST901",)}

    with pytest.raises(ValueError, match=unknown):
        Mission(**{**fields, **changes})


def test_two_missions_flying_the_same_flight_are_refused(tree: Path) -> None:
    """The same vehicle, FSW and scenario cannot be flown twice, whatever each judges.

    Args:
        tree: the tree.
    """
    fsw = claiming("SYS901")
    one = Mission(VEHICLE, fsw, ("TST901",), rungs=("SRS901",))
    two = Mission(VEHICLE, fsw, ("TST901",), rungs=("SRS902",))

    with pytest.raises(ValueError, match="TST901"):
        mission_tests(one, two)


@pytest.fixture
def project(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A pytester project whose root holds the tree.

    Args:
        pytester: the pytester fixture.
        monkeypatch: the monkeypatch fixture.

    Returns:
        The pytester.
    """
    write_tree(pytester.path)
    monkeypatch.setattr(requirements_tree, "ROOT", pytester.path)
    pytester.mkdir("scenarios")
    (pytester.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=1.0, body="pass"))
    return pytester


def test_flight_json_survives_a_case_that_crashes_before_it_flies(
    project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A case that crashes setting up `sim_scenario` still leaves its flight's facts.

    Two missions fly one vehicle: one judges every rung, one a filter. Each flight's folder holds
    `flight.json` with the scenario, the FSW builder's name, the sorted capabilities and the filter
    or null, and no `build`, since no host was built.

    Args:
        project: the project.
        monkeypatch: the monkeypatch fixture.
    """
    from wise_dynamics.basilisk.scenarios import SCENARIOS

    def boom(self: object, *args: object, **kwargs: object) -> None:
        """Fail as a dispersion that cannot be drawn.

        Args:
            self: the scenario.
            *args: unused.
            **kwargs: unused.

        Raises:
            RuntimeError: always.
        """
        raise RuntimeError("dispersion failed")

    monkeypatch.setattr(SCENARIOS["leo500"], "disperse", boom)
    project.makepyfile(
        test_flights="""
from harness.mission import Mission, mission_tests, provides


@provides("SYS902", "SYS901")
def everything(scenario):
    raise AssertionError("never built")


@provides("SYS901")
def narrowed(scenario):
    raise AssertionError("never built")


globals().update(
    mission_tests(
        Mission(vehicle="imu_spacecraft", fsw=everything, scenarios=("TST901",)),
        Mission(
            vehicle="imu_spacecraft", fsw=narrowed, scenarios=("TST901",), rungs=("SRS902",)
        ),
    )
)
"""
    )

    result = project.runpytest_inprocess("-p", "no:cacheprovider")

    result.assert_outcomes(errors=2)
    result.stdout.fnmatch_lines(["*dispersion failed*"])

    found = {path.parent.name: path for path in project.path.rglob("flight.json")}
    assert sorted(found) == ["test_everything_alpha", "test_narrowed_alpha"]
    assert found["test_everything_alpha"].parts[-5:-1] == (
        "scratch",
        "test_flights",
        "Test_imu_spacecraft",
        "test_everything_alpha",
    )
    assert json.loads(found["test_everything_alpha"].read_text()) == {
        "scenario": "TST901",
        "fsw": "everything",
        "capabilities": ["SYS901", "SYS902"],
        "rungs": None,
    }
    assert json.loads(found["test_narrowed_alpha"].read_text()) == {
        "scenario": "TST901",
        "fsw": "narrowed",
        "capabilities": ["SYS901"],
        "rungs": ["SRS902"],
    }


def test_a_failing_check_fails_the_case_with_its_messages_and_the_run_file_is_plain(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """The check's messages are in the failure; the run file carries no GNC attribute.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    project.makepyfile(
        test_flights=STUB_HOST
        + """
from harness.mission import Mission, mission_tests, provides


@provides("SYS901")
def stub_fsw(scenario):
    return StubHost()


def check(path):
    return ["the first problem", "the second problem"]


globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", fsw=stub_fsw, scenarios=("TST901",), check=check
        )
    )
)
"""
    )

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*the first problem*", "*the second problem*"])
    [path] = project.path.rglob("run_0000.h5")
    with h5py.File(path, "r") as f:
        gnc = [name for name in f.attrs if "gnc" in name.lower()]
        assert gnc == []
        assert not {"vehicle", "scenario_item", "capabilities"} & set(f.attrs)


def test_a_check_is_given_the_cases_run_file_and_a_passing_check_passes(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """`check` receives the finished case's run file; returning no messages passes the case.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    project.makepyfile(
        test_flights=STUB_HOST
        + """
import h5py

from harness.mission import Mission, mission_tests, provides


@provides("SYS901")
def stub_fsw(scenario):
    return StubHost()


def check(path):
    with h5py.File(path, "r") as f:
        if "commands" not in f.attrs or "truth" not in f:
            return ["not the case's run file"]
    return []


globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", fsw=stub_fsw, scenarios=("TST901",), check=check
        )
    )
)
"""
    )

    fly_in_a_subprocess(project).assert_outcomes(passed=1)


def test_a_notebook_can_fly_a_scenario_it_defines_before_its_missions(
    project: pytest.Pytester,
) -> None:
    """A file whose TST item references itself finds its own definition while it loads.

    Args:
        project: the project.
    """
    write_tree(project.path, alpha_path="test_self.py")
    project.makepyfile(
        test_self="""
import pytest

from harness.mission import Mission, mission_tests, provides


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s(1.0)
@pytest.mark.sim_runs(1)
def alpha():
    pass


@provides("SYS901")
def fsw(scenario):
    raise AssertionError("never built")


globals().update(
    mission_tests(Mission(vehicle="imu_spacecraft", fsw=fsw, scenarios=("TST901",)))
)
"""
    )

    result = project.runpytest_inprocess("--collect-only", "-q", "-p", "no:cacheprovider")

    result.stdout.fnmatch_lines(["*Test_imu_spacecraft::test_fsw_alpha*"])


def test_a_scenario_file_that_raised_on_import_is_imported_afresh_once_fixed(
    tree: Path,
) -> None:
    """A failed import leaves nothing registered, so the lookup after the fix succeeds.

    Args:
        tree: the tree.
    """
    scenarios = tree / "scenarios"
    scenarios.mkdir()
    (scenarios / "alpha.py").write_text('raise RuntimeError("alpha is broken")\n')
    mission = Mission(VEHICLE, claiming("SYS901"), ("TST901",))

    with pytest.raises(RuntimeError, match="alpha is broken"):
        mission_tests(mission)

    (scenarios / "alpha.py").write_text(ALPHA.format(duration=1.0, body="pass"))
    [vehicle_class] = mission_tests(mission).values()
    assert [name for name in vars(vehicle_class) if name.startswith("test_")] == [
        "test_build_alpha"
    ]


def test_flying_a_scenario_before_defining_it_is_an_error(project: pytest.Pytester) -> None:
    """A file whose missions come before the definition they reference fails, naming it.

    Args:
        project: the project.
    """
    write_tree(project.path, alpha_path="test_self.py")
    project.makepyfile(
        test_self="""
import pytest

from harness.mission import Mission, mission_tests, provides


@provides("SYS901")
def fsw(scenario):
    raise AssertionError("never built")


globals().update(
    mission_tests(Mission(vehicle="imu_spacecraft", fsw=fsw, scenarios=("TST901",)))
)


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_runs(1)
def alpha():
    pass
"""
    )

    result = project.runpytest_inprocess("--collect-only", "-q", "-p", "no:cacheprovider")

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*ValueError*alpha*"])


STUB_HOST = """
from Basilisk.architecture import sysModel


class StubHost(sysModel.SysModel):
    period_s = 1.0
    build = {"host": "stub", "revision": "r1"}
    dictionary = None
    failure = None

    def Reset(self, CurrentSimNanos):
        pass

    def UpdateState(self, CurrentSimNanos):
        pass

    def uplink(self, name, args, context):
        raise AssertionError("no command is sent")

    def responses(self):
        return []

    def telemetry(self):
        return []

    def values(self, name, raws):
        raise AssertionError("nothing is written")
"""


STUB_FLIGHT = """
from harness.mission import Mission, mission_tests, provides


@provides("SYS901")
def stub_fsw(scenario):
    return StubHost()


globals().update(
    mission_tests(Mission(vehicle="imu_spacecraft", fsw=stub_fsw, scenarios=("TST901",)))
)
"""


def test_a_flight_runs_the_procedure_on_the_host_s_radio_edge_for_the_scenario_s_duration(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """A host that is neither built-in type flies through the ground, which records the run.

    The stub host presents a radio edge and writes nothing. The run file holds the truth and an
    empty command log, no telemetry, and ends at the TST definition's `sim_duration_s`, so the
    harness bound the stopping rule. `flight.json` names the builder and the stub's `build`.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    (project.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=20.0, body="pass"))
    project.makepyfile(test_flights=STUB_HOST + STUB_FLIGHT)

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=1)
    [path] = project.path.rglob("run_0000.h5")
    with h5py.File(path, "r") as f:
        assert "tlm" not in f
        assert json.loads(f.attrs["commands"]) == []
        assert "r_N" in f["truth"]
        assert f["t_s"][-1] == 20.0
    [flight] = project.path.rglob("flight.json")
    assert json.loads(flight.read_text()) == {
        "scenario": "TST901",
        "capabilities": ["SYS901"],
        "rungs": None,
        "fsw": "stub_fsw",
        "build": {"host": "stub", "revision": "r1"},
    }


def test_the_definition_s_ground_period_mark_sets_the_ground_s_period(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """A definition marked `sim_ground_period_s(10.0)` is flown by a ground with that period.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    definition = ALPHA.format(duration=20.0, body="assert ground.period_s == 10.0")
    (project.path / "scenarios" / "alpha.py").write_text(
        definition.replace(
            "@pytest.mark.sim_runs(1)",
            "@pytest.mark.sim_runs(1)\n@pytest.mark.sim_ground_period_s(10.0)",
        )
    )
    project.makepyfile(test_flights=STUB_HOST + STUB_FLIGHT)

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=1)


def test_a_procedure_s_exception_fails_the_case_as_itself(
    project: pytest.Pytester,
    fly_in_a_subprocess: Callable[..., pytest.RunResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A procedure waiting for what never comes fails the case with its own `TimeoutError`.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
        monkeypatch: widens the subprocess's summary line to hold the exception.
    """
    (project.path / "scenarios" / "alpha.py").write_text(
        ALPHA.format(duration=20.0, body="await ground.until(lambda: False, timeout_s=3.0)")
    )
    project.makepyfile(test_flights=STUB_HOST + STUB_FLIGHT)

    monkeypatch.setenv("COLUMNS", "200")
    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        ["FAILED *TimeoutError: timed out at t = 3.0 s waiting until the condition at alpha.py:*"]
    )
    assert list(project.path.rglob("run_0000.h5")) == []


def test_a_procedure_still_waiting_when_the_flight_ends_fails_the_case_naming_its_wait(
    project: pytest.Pytester,
    fly_in_a_subprocess: Callable[..., pytest.RunResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A procedure sleeping past the flight's 20 s fails the case, naming what it waited for.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
        monkeypatch: widens the subprocess's summary line to hold the exception.
    """
    (project.path / "scenarios" / "alpha.py").write_text(
        ALPHA.format(duration=20.0, body="await ground.sleep(100.0)")
    )
    project.makepyfile(test_flights=STUB_HOST + STUB_FLIGHT)
    monkeypatch.setenv("COLUMNS", "200")

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        ["FAILED *TimeoutError: the flight ended at t = 20.0 s * waiting until t = 100.0 s"]
    )


def test_a_procedure_that_forgets_an_await_fails_the_case(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """Under the repository's warning filters, a `ground.sleep` never awaited fails the case.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    filters = pyproject["tool"]["pytest"]["ini_options"]["filterwarnings"]
    project.makeini("[pytest]\nfilterwarnings =\n" + "".join(f"    {f}\n" for f in filters))
    (project.path / "scenarios" / "alpha.py").write_text(
        ALPHA.format(duration=3.0, body="ground.sleep(1.0)")
    )
    project.makepyfile(test_flights=STUB_HOST + STUB_FLIGHT)

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*coroutine 'Ground.sleep' was never awaited*"])


def test_an_exception_in_the_flight_software_fails_the_case_as_itself(
    project: pytest.Pytester,
    fly_in_a_subprocess: Callable[..., pytest.RunResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bug in a hosted toy algorithm's `step` fails the case with that exception, not Basilisk's.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
        monkeypatch: widens the subprocess's summary line to hold the exception.
    """
    (project.path / "Toy.fpp").write_text(
        "module Toy {\n"
        "  passive component Toy {\n"
        "    telemetry count: U32\n"
        "    time get port timeCaller\n"
        "    telemetry port tlmOut\n"
        "  }\n"
        "}\n"
    )
    project.makepyfile(
        test_flights="""
from pathlib import Path

from fsw.python import AlgorithmModule
from ground.dictionary import Dictionary
from harness.mission import Mission, mission_tests, provides


class Broken:
    def step(self, t):
        raise ZeroDivisionError("the step's own bug")


@provides("SYS901")
def toy(scenario):
    model = [Path(__file__).with_name("Toy.fpp")]
    dictionary = Dictionary.from_component(model, "Toy.Toy", instance="toy")
    readers = scenario.vehicle.readers()
    return AlgorithmModule(Broken(), readers, instance="toy", dictionary=dictionary)


globals().update(
    mission_tests(Mission(vehicle="imu_spacecraft", fsw=toy, scenarios=("TST901",)))
)
"""
    )

    monkeypatch.setenv("COLUMNS", "200")
    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["FAILED *ZeroDivisionError: the step's own bug*"])


def test_a_later_cases_base_write_keeps_the_build_an_earlier_case_merged(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """Case 0 builds the stub host; case 1's builder raises, and `flight.json` still has `build`.

    Case 1's fixture writes the flight's base facts before its builder raises, so the base write
    must merge into the file rather than replace it.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    (project.path / "scenarios" / "alpha.py").write_text(
        ALPHA.format(duration=1.0, body="pass").replace("sim_runs(1)", "sim_runs(2)")
    )
    project.makepyfile(
        test_flights=STUB_HOST
        + """
from harness.mission import Mission, mission_tests, provides

BUILT = []


@provides("SYS901")
def stub_fsw(scenario):
    BUILT.append(scenario)
    if len(BUILT) > 1:
        raise RuntimeError("the second case cannot build its host")
    return StubHost()


globals().update(
    mission_tests(Mission(vehicle="imu_spacecraft", fsw=stub_fsw, scenarios=("TST901",)))
)
"""
    )

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*the second case cannot build its host*"])
    [flight] = project.path.rglob("flight.json")
    assert json.loads(flight.read_text()) == {
        "scenario": "TST901",
        "capabilities": ["SYS901"],
        "rungs": None,
        "fsw": "stub_fsw",
        "build": {"host": "stub", "revision": "r1"},
    }


def test_an_interrupted_flight_json_write_leaves_the_old_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write goes to a temporary file beside the target and lands by `os.replace`.

    A write interrupted where it would land raises, leaves the previous file whole and leaves no
    temporary file behind.

    Args:
        tmp_path: the test's directory.
        monkeypatch: the monkeypatch fixture.
    """
    from harness.mission import _merge_json

    target = tmp_path / "flight.json"
    _merge_json(target, {"scenario": "TST901"})
    landed: list[Path] = []

    def interrupted(source: str | Path, destination: str | Path) -> None:
        """Record the source and fail as a write killed at the rename.

        Args:
            source: the temporary file.
            destination: the file it would land as.

        Raises:
            OSError: always.
        """
        landed.append(Path(source))
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", interrupted)

    with pytest.raises(OSError, match="interrupted"):
        _merge_json(target, {"build": {"host": "stub"}})

    assert json.loads(target.read_text()) == {"scenario": "TST901"}
    [source] = landed
    assert source.parent == tmp_path
    assert source != target
    assert list(tmp_path.iterdir()) == [target]
