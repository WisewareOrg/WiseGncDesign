"""Missions: what a flight judges, what a mission refuses, and the record a flight leaves.

Every test but the F´ build's reads a requirements tree it writes in `tmp_path`, by pointing the
tree root at it, so none depends on the repository's own tree; the F´ build's test flies the
repository's configurations through the repository's tree. The tree holds two capabilities, four
rungs and two scenarios:

    SYS901 <- SRS901, SRS902, SRS904      SYS902 <- SRS903
    TST901 links SRS901, SRS902, SRS903   TST902 links SRS902

The missions fly the harness's test mock, `harness.mock.MOCK`, on the Python build: `FirstMockOnly`
claims SYS901, `SecondMockOnly` SYS902 and `BothMocks` both.
"""

import json
import os
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import h5py
import pytest
import yaml
from wise_dynamics.basilisk.vehicles import VEHICLES

from fsw.codegen.deployment import configuration_model
from fsw.codegen.members import members
from harness import requirements_tree
from harness.mission import Mission, _claims, mission_tests
from harness.mock import MOCK

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


def mission(gnc: str, scenarios: tuple[str, ...] = ("TST901",), **fields: Any) -> Mission:
    """A mission flying a test mock configuration on the Python build.

    Args:
        gnc: the test mock's configuration.
        scenarios: the TST IDs.
        **fields: the mission's other fields.

    Returns:
        The mission.
    """
    return Mission(VEHICLE, gnc, "python", scenarios, contract=MOCK, **fields)


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
    assert mission("FirstMockOnly").rungs is None


def test_a_filter_rung_outside_the_scenarios_is_refused(tree: Path) -> None:
    """SRS904 is under SYS901 but no scenario of the mission links it.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="SRS904"):
        mission("FirstMockOnly", rungs=("SRS904",))


def test_a_flight_with_no_rungs_is_refused(tree: Path) -> None:
    """A configuration claiming SYS902 judges nothing in TST902, which links only SRS902.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="TST902"):
        mission("SecondMockOnly", ("TST902",))


def test_a_filter_that_empties_one_scenarios_flight_is_refused_naming_it(tree: Path) -> None:
    """SRS901 is linked by TST901 only, so the filter leaves TST902 with no rung to judge.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="TST902"):
        mission("FirstMockOnly", ("TST901", "TST902"), rungs=("SRS901",))


def test_a_filter_answered_by_every_scenarios_flight_is_accepted(tree: Path) -> None:
    """SRS902 is linked by both TST901 and TST902, so each flight keeps a rung under the filter.

    Args:
        tree: the tree.
    """
    assert mission("FirstMockOnly", ("TST901", "TST902"), rungs=("SRS902",)).rungs == ("SRS902",)


def test_a_configuration_claiming_nothing_one_scenario_links_is_refused_naming_it(
    tree: Path,
) -> None:
    """SYS902 owns SRS903, which TST901 links but TST902 does not.

    Args:
        tree: the tree.
    """
    with pytest.raises(ValueError, match="TST902"):
        mission("SecondMockOnly", ("TST901", "TST902"))


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
    with pytest.raises(ValueError, match=unknown):
        mission("FirstMockOnly").but(**changes)


@pytest.mark.parametrize(
    ("changes", "named"),
    [
        ({"gnc": "NoSuchConfiguration"}, r"NoSuchConfiguration.*'BothMocks'.*'FirstMockOnly'"),
        ({"build": "simulink"}, r"simulink.*'fprime'.*'python'"),
        ({"build": "fprime"}, r"fprime.*harness/mock"),
        ({"gnc": "Unclaimed"}, r"HarnessMock\.UnclaimedMock.*faulty_mock/UnclaimedMock\.fpp"),
        ({"gnc": "Classless"}, r"harness\.mock\.faulty_mock\.faulty_mock.*ClasslessMock"),
        ({"gnc": "Parameterless"}, r"harness\.mock\.faulty_mock\.faulty_mock\.parameters"),
    ],
)
def test_each_lookup_that_fails_is_refused_naming_what_it_looked_for(
    tree: Path, changes: dict, named: str
) -> None:
    """A configuration, build, claim, class or `parameters` not found is a ValueError naming it.

    An unknown configuration names the contract's; an unknown build names both builds; the F´ build
    of a contract other than the repository's names the contract; a member's component with no
    `@ provides` names it and its file; a member's class missing from its notebook names the
    notebook's module and the class; and a member with parameters and no `parameters` names the
    function. A vehicle missing a role the configuration takes is refused by each build's tick,
    naming the role, as `fsw/python/platform/frame_runner_test.py` and `lab/adapter_test.py` show.

    Args:
        tree: the tree.
        changes: the field replaced.
        named: what the refusal names, as a pattern.
    """
    with pytest.raises(ValueError, match=named):
        mission("FirstMockOnly").but(**changes)


def test_a_claim_the_tree_lacks_is_refused_naming_it_and_its_component(tree: Path) -> None:
    """`FirstMock` claims SYS901, which this tree does not hold.

    Args:
        tree: the tree, SYS901 removed from it.
    """
    (tree / "docs" / "requirements" / "sys" / "SYS901.yml").unlink()

    with pytest.raises(ValueError, match=r"SYS901.*HarnessMock\.FirstMock"):
        mission("FirstMockOnly")


def test_a_configuration_claims_the_union_of_its_members_claims(tree: Path) -> None:
    """`BothMocks` judges SRS903, which only SYS902 owns, and SRS901, which only SYS901 owns.

    Args:
        tree: the tree.
    """
    both = mission("BothMocks", rungs=("SRS901", "SRS903"))

    assert both.rungs == ("SRS901", "SRS903")
    with pytest.raises(ValueError, match="SRS903"):
        mission("FirstMockOnly", rungs=("SRS901", "SRS903"))


def test_an_fprime_mission_is_built_without_its_configuration_s_extension(
    configuration: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No lookup of the F´ build's reaches the extension; only a case's `lab.Adapter` needs it.

    Each configuration flies the repository's tree through the first scenario that judges a rung
    under its claims, with its extension made absent.

    Args:
        configuration: the configuration.
        monkeypatch: makes the configuration's extension absent.
    """
    monkeypatch.setitem(sys.modules, f"lab._wise_fsw_{configuration}", None)
    model = configuration_model(configuration)
    claims = {
        uid
        for group in members(model, configuration).values()
        for instance in group
        for uid in _claims(model, model.components[instance.component])
    }
    scenario = next(
        uid for uid in requirements_tree.items("TST") if requirements_tree.flight_rungs(uid, claims)
    )

    flown = Mission(sorted(VEHICLES)[0], configuration, "fprime", (scenario,))

    assert (flown.gnc, flown.build) == (configuration, "fprime")


def test_two_missions_flying_the_same_flight_are_refused(tree: Path) -> None:
    """A vehicle, configuration, build and scenario cannot be flown twice, whatever each judges.

    Args:
        tree: the tree.
    """
    one = mission("FirstMockOnly", rungs=("SRS901",))
    two = mission("FirstMockOnly", rungs=("SRS902",))

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
    `flight.json` with the scenario, the configuration and build flown, the sorted capabilities and
    the filter or null, and no `build`, since no host was built.

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
from harness.mission import Mission, mission_tests
from harness.mock import MOCK

globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="BothMocks", build="python", scenarios=("TST901",),
            contract=MOCK,
        ),
        Mission(
            vehicle="imu_spacecraft", gnc="FirstMockOnly", build="python", scenarios=("TST901",),
            rungs=("SRS902",), contract=MOCK,
        ),
    )
)
"""
    )

    result = project.runpytest_inprocess("-p", "no:cacheprovider")

    result.assert_outcomes(errors=2)
    result.stdout.fnmatch_lines(["*dispersion failed*"])

    found = {path.parent.name: path for path in project.path.rglob("flight.json")}
    both, first = "test_BothMocks_python_alpha", "test_FirstMockOnly_python_alpha"
    assert sorted(found) == [both, first]
    assert found[both].parts[-5:-1] == ("scratch", "test_flights", "Test_imu_spacecraft", both)
    assert json.loads(found[both].read_text()) == {
        "scenario": "TST901",
        "fsw": {"gnc": "BothMocks", "build": "python"},
        "capabilities": ["SYS901", "SYS902"],
        "rungs": None,
    }
    assert json.loads(found[first].read_text()) == {
        "scenario": "TST901",
        "fsw": {"gnc": "FirstMockOnly", "build": "python"},
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
        test_flights="""
from harness.mission import Mission, mission_tests
from harness.mock import MOCK


def check(path):
    return ["the first problem", "the second problem"]


globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="FirstMockOnly", build="python", scenarios=("TST901",),
            check=check, contract=MOCK,
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
        test_flights="""
import h5py

from harness.mission import Mission, mission_tests
from harness.mock import MOCK


def check(path):
    with h5py.File(path, "r") as f:
        if "commands" not in f.attrs or "truth" not in f:
            return ["not the case's run file"]
    return []


globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="FirstMockOnly", build="python", scenarios=("TST901",),
            check=check, contract=MOCK,
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

from harness.mission import Mission, mission_tests
from harness.mock import MOCK


@pytest.mark.sim_scenario("leo500")
@pytest.mark.sim_duration_s(1.0)
@pytest.mark.sim_runs(1)
def alpha():
    pass


globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="FirstMockOnly", build="python", scenarios=("TST901",),
            contract=MOCK,
        )
    )
)
"""
    )

    result = project.runpytest_inprocess("--collect-only", "-q", "-p", "no:cacheprovider")

    result.stdout.fnmatch_lines(["*Test_imu_spacecraft::test_FirstMockOnly_python_alpha*"])


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
    flown = mission("FirstMockOnly")

    with pytest.raises(RuntimeError, match="alpha is broken"):
        mission_tests(flown)

    (scenarios / "alpha.py").write_text(ALPHA.format(duration=1.0, body="pass"))
    [vehicle_class] = mission_tests(flown).values()
    assert [name for name in vars(vehicle_class) if name.startswith("test_")] == [
        "test_FirstMockOnly_python_alpha"
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

from harness.mission import Mission, mission_tests
from harness.mock import MOCK

globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="FirstMockOnly", build="python", scenarios=("TST901",),
            contract=MOCK,
        )
    )
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


FLIGHT = """
from harness.mission import Mission, mission_tests
from harness.mock import MOCK

globals().update(
    mission_tests(
        Mission(
            vehicle="imu_spacecraft", gnc="FirstMockOnly", build="python", scenarios=("TST901",),
            contract=MOCK,
        )
    )
)
"""
"""A notebook flying `FirstMockOnly` on the Python build through TST901."""


def test_a_flight_runs_the_procedure_on_the_build_s_radio_edge_for_the_scenario_s_duration(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """The configuration's build, hosted by `FswHost`, flies through the ground on its radio edge.

    The test mock writes nothing. The run file holds the truth and an empty command log, no
    telemetry, and ends at the TST definition's `sim_duration_s`, so the harness bound the stopping
    rule. `flight.json` names the configuration and build flown, and the build's identity.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    (project.path / "scenarios" / "alpha.py").write_text(ALPHA.format(duration=20.0, body="pass"))
    project.makepyfile(test_flights=FLIGHT)

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
        "fsw": {"gnc": "FirstMockOnly", "build": "python"},
        "build": {"host": "fsw.python.FrameRunner"},
    }


def test_a_case_s_parameter_record_is_written_beside_its_run_file_from_each_member(
    project: pytest.Pytester, fly_in_a_subprocess: Callable[..., pytest.RunResult]
) -> None:
    """Each member's tuple, from its notebook's `parameters`, under its qualified instance.

    `FirstMock`'s gain is the case's scenario's Earth `mu`; `SecondMock` has no parameter and no
    `parameters`, so its entry is empty.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
    """
    project.makepyfile(test_flights=FLIGHT.replace("FirstMockOnly", "BothMocks"))

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(passed=1)
    [run] = project.path.rglob("run_0000.h5")
    record = json.loads(run.with_suffix(".prm.json").read_text())
    assert record == {"BothMocks.first": {"gain": 3.986004360e14}, "BothMocks.second": {}}


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
    project.makepyfile(test_flights=FLIGHT)

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
    project.makepyfile(test_flights=FLIGHT)

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
    project.makepyfile(test_flights=FLIGHT)
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
    project.makepyfile(test_flights=FLIGHT)

    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*coroutine 'Ground.sleep' was never awaited*"])


def test_an_exception_in_the_flight_software_fails_the_case_as_itself(
    project: pytest.Pytester,
    fly_in_a_subprocess: Callable[..., pytest.RunResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bug in an algorithm's step fails the case with that exception, not Basilisk's.

    The procedure commands `FirstMock` to fail, and its next step raises.

    Args:
        project: the project.
        fly_in_a_subprocess: runs the project in a subprocess.
        monkeypatch: widens the subprocess's summary line to hold the exception.
    """
    (project.path / "scenarios" / "alpha.py").write_text(
        ALPHA.format(duration=20.0, body='await ground.send("first.fail")')
    )
    project.makepyfile(test_flights=FLIGHT)

    monkeypatch.setenv("COLUMNS", "200")
    result = fly_in_a_subprocess(project)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["FAILED * - ZeroDivisionError: the tick's own bug"])


def test_a_later_cases_base_write_keeps_the_build_an_earlier_case_merged(
    project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A case that crashes in setup after its base write leaves the `build` already recorded.

    `flight.json` holds the `build` an earlier case merged. This case's fixture writes the flight's
    base facts, then its scenario fails to disperse, so the base write must merge into the file
    rather than replace it.

    Args:
        project: the project.
        monkeypatch: makes the scenario's dispersion fail.
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
    flight = project.path.joinpath(
        "monte_carlo",
        "scratch",
        "test_flights",
        "Test_imu_spacecraft",
        "test_FirstMockOnly_python_alpha",
        "flight.json",
    )
    flight.parent.mkdir(parents=True)
    flight.write_text(json.dumps({"build": {"host": "fsw.python.FrameRunner"}}))
    project.makepyfile(test_flights=FLIGHT)

    result = project.runpytest_inprocess("-p", "no:cacheprovider")

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*dispersion failed*"])
    assert json.loads(flight.read_text()) == {
        "scenario": "TST901",
        "capabilities": ["SYS901"],
        "rungs": None,
        "fsw": {"gnc": "FirstMockOnly", "build": "python"},
        "build": {"host": "fsw.python.FrameRunner"},
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
