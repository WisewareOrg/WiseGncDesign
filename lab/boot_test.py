"""The pin's boot: PrmDb loads the case's parameter file, and a parameter left invalid fails it.

Skipped without the deployment `just fsw` builds.
"""

import itertools
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from fsw.codegen.dictionary import Dictionary
from ground import parameters
from ground.fprime_station import FprimeStation
from lab import dictionary_path

NS = 1_000_000_000
"""ns per s."""


def _id(dictionary: Dictionary, name: str) -> int:
    """A parameter's ID.

    Args:
        dictionary: the deployment's dictionary.
        name: `<instance>.<parameter>`.

    Returns:
        Its ID.
    """
    return next(i for i, p in dictionary.parameters_by_id.items() if p.name == name)


def test_a_case_s_file_boots_every_parameter_valid(
    booted: ModuleType,
    dictionary: Dictionary,
    prm_record: Path,
):
    """The case's record holds every parameter of the deployment, and the copy boots on it.

    Args:
        booted: the test's copy of the deployment, which boots on the record or fails.
        dictionary: the copy's dictionary.
        prm_record: the case's parameter record.
    """
    recorded = {
        f"{instance.rsplit('.', 1)[1]}.{name}"
        for instance, values in json.loads(prm_record.read_text()).items()
        for name in values
    }
    assert recorded == {p.name for p in dictionary.parameters_by_id.values()}


def test_a_missing_file_fails_the_boot(fsw: ModuleType, tmp_path: Path, parameter_ids: list[int]):
    """No file at the path leaves every parameter invalid, each named.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    missing = tmp_path / "run_0000.prm.dat"
    named = ", ".join(map(str, parameter_ids))

    with pytest.raises(RuntimeError, match=f"parameters {named} are not valid"):
        fsw.boot(str(missing), parameter_ids)


def test_a_parameter_missing_from_the_record_fails_the_boot(
    fsw: ModuleType,
    configuration: str,
    dictionary: Dictionary,
    prm_record: Path,
    parameter_ids: list[int],
):
    """A record without one parameter makes a `.dat` without it; boot names that parameter alone.

    Args:
        fsw: the test's copy.
        configuration: the copy's configuration.
        dictionary: the copy's dictionary.
        prm_record: the case's parameter record, edited here.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    entries = json.loads(prm_record.read_text())
    instance, values = next(iter(entries.items()))
    parameter = next(iter(values))
    del values[parameter]
    prm_record.write_text(json.dumps(entries))
    dropped = _id(dictionary, f"{instance.rsplit('.', 1)[1]}.{parameter}")

    with pytest.raises(RuntimeError, match=rf"^parameters {dropped} are not valid"):
        fsw.boot(str(parameters.dat(prm_record, dictionary_path(configuration))), parameter_ids)


def _changed(value: object, counter: Iterator[int]) -> object:
    """A record's value with each of its numbers raised by the next count, so no two are equal.

    Args:
        value: a parameter's value as the record holds it, a number or nested lists of numbers.
        counter: the counts, each used once.

    Returns:
        The changed value, of the same shape.
    """
    if isinstance(value, list):
        return [_changed(v, counter) for v in value]
    return value + next(counter)


def test_prm_db_s_saved_image_decodes_to_the_edited_record(
    fsw: ModuleType,
    configuration: str,
    station: FprimeStation,
    tmp_path: Path,
    prm_record: Path,
    parameter_ids: list[int],
    bus: list[tuple[int, bytes]],
):
    """Every value edited in the record is the one PrmDb holds, read back from its own image.

    The `.dat` is removed once booted, so the file decoded is the one `PRM_SAVE_FILE` writes.
    F´'s `fprime-prm-decode` is always given `-o`, since it would otherwise overwrite the record.

    Args:
        fsw: the test's copy.
        configuration: the copy's configuration.
        station: the station on it.
        tmp_path: where PrmDb's image is decoded.
        prm_record: the case's parameter record, edited here.
        parameter_ids: every parameter's ID, which boot holds valid.
        bus: every role's bus message on its LabBusDriver port.
    """
    entries = json.loads(prm_record.read_text())
    counter = itertools.count(1)
    edited = {
        instance: {name: _changed(value, counter) for name, value in values.items()}
        for instance, values in entries.items()
    }
    assert edited != entries
    prm_record.write_text(json.dumps(edited))
    dat = parameters.dat(prm_record, dictionary_path(configuration))
    fsw.boot(str(dat), parameter_ids)
    dat.unlink()

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 1)
    fsw.step(t_ns=NS, bus=bus)
    image = tmp_path / "image.json"
    tool = Path(sys.executable).parent / "fprime-prm-decode"
    command = [tool, dat, "-d", dictionary_path(configuration), "-o", image]
    subprocess.run(command, check=True, capture_output=True)

    assert station.responses() == [(1, "OK", None)]
    assert json.loads(image.read_text()) == edited


@pytest.mark.parametrize("path", ["run_0000.prm.dat", "/run_0000.prm.dat"])
def test_a_relative_path_or_one_in_the_root_is_refused(
    fsw: ModuleType, path: str, parameter_ids: list[int]
):
    """The sandbox is the file's directory, which is never the root, so neither path boots.

    Args:
        fsw: the test's copy.
        path: the parameter file's path.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    with pytest.raises(ValueError, match="not an absolute path in a directory below the root"):
        fsw.boot(path, parameter_ids)


def _of_length(directory: Path, length: int, fill: str) -> Path:
    """A path in `directory` of exactly `length` characters, its last name made of `fill`.

    Args:
        directory: where the path ends.
        length: its length in characters.
        fill: the character its last name repeats.

    Returns:
        The path.
    """
    path = directory / (fill * (length - len(str(directory)) - 1))
    assert len(str(path)) == length, f"{directory} is too long to make a {length}-character path"
    return path


@pytest.mark.parametrize(("past", "boots"), [(0, True), (1, False)])
def test_a_file_s_path_longer_than_f_prime_s_file_names_is_refused_before_loading(
    fsw: ModuleType,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
    configuration: str,
    past: int,
    boots: bool,
):
    """F´'s `FileNameStringSize` less its terminator is the longest path; a longer one is refused.

    Args:
        fsw: the test's copy.
        tmp_path: where the path is made.
        prm: the case's parameter file, copied to the path.
        parameter_ids: every parameter's ID, which boot holds valid.
        configuration: the copy's configuration, whose dictionary gives `FileNameStringSize`.
        past: how many bytes the path runs past the longest F´ holds.
        boots: whether the copy boots on it.
    """
    constants = json.loads(dictionary_path(configuration).read_text())["constants"]
    longest = next(c["value"] for c in constants if c["qualifiedName"] == "FileNameStringSize") - 1
    path = _of_length(tmp_path, longest + past, "x")
    shutil.copyfile(prm, path)

    if boots:
        fsw.boot(str(path), parameter_ids)
    else:
        refusal = f" is {longest + past} bytes, past F´'s limit of {longest} "
        with pytest.raises(ValueError, match=refusal):
            fsw.boot(str(path), parameter_ids)


def _load_file(station: FprimeStation, dictionary: Dictionary, path: Path) -> bytes:
    """`prmDb.PRM_LOAD_FILE`'s packet, merging, its string argument serialized by hand.

    The station codes no string argument, so the packet is built here: the header the station
    gives a command, then F´'s string, its length as `FwSizeStoreType` before its bytes, then the
    merge enumeration's `MERGE`. A command's string holds at most `FW_CMD_STRING_MAX_SIZE`, 40
    characters, so the path is a short relative one.

    Args:
        station: the station on the copy.
        dictionary: the copy's dictionary.
        path: the file to load, relative to the working directory.

    Returns:
        The packet.
    """
    command = dictionary.command("prmDb.PRM_LOAD_FILE")
    header = station.encode_command("prmDb.PRM_SAVE_FILE", {})
    header = header[: -dictionary.type("FwOpcodeType").dtype.itemsize]
    header += dictionary.type("FwOpcodeType").serialized([command.opcode]).tobytes()
    name = str(path).encode()
    size = dictionary.type("FwSizeStoreType").serialized([len(name)]).tobytes()
    return header + size + name + bytes([0])


def test_the_sandbox_is_the_case_s_directory(
    fsw: ModuleType,
    station: FprimeStation,
    dictionary: Dictionary,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
    monkeypatch: pytest.MonkeyPatch,
    bus: list[tuple[int, bytes]],
):
    """PrmDb saves to the case's file and loads one beside it, but none from another directory.

    Args:
        fsw: the test's copy.
        station: the station on it.
        dictionary: the copy's dictionary.
        tmp_path: the test's directory, holding the case's directory `case` and `elsewhere`.
        prm: the case's parameter file, in `case`.
        parameter_ids: every parameter's ID, which boot holds valid.
        monkeypatch: sets the working directory, which the loaded paths are relative to.
        bus: every role's bus message on its LabBusDriver port.
    """
    monkeypatch.chdir(tmp_path)
    dat = Path(prm)
    case, elsewhere = dat.parent, tmp_path / "elsewhere"
    assert case == tmp_path / "case"
    elsewhere.mkdir()
    shutil.copyfile(dat, case / "beside.dat")
    shutil.copyfile(dat, elsewhere / "outside.dat")
    fsw.boot(prm, parameter_ids)
    dat.unlink()

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 1)
    fsw.uplink(_load_file(station, dictionary, Path("elsewhere/outside.dat")), 2)
    fsw.uplink(_load_file(station, dictionary, Path("case/beside.dat")), 3)
    fsw.step(t_ns=NS, bus=bus)

    assert station.responses() == [(1, "OK", None), (2, "EXECUTION_ERROR", None), (3, "OK", None)]
    assert dat.exists()
