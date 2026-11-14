"""The pin's boot: PrmDb loads the case's parameter file, and a parameter left invalid fails it.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
import itertools
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from ground import parameters
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY as DICTIONARY_PATH

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

DICTIONARY = Dictionary(DICTIONARY_PATH)
"""The deployment's dictionary, which the build generated."""

NS = 1_000_000_000
"""ns per s."""


def _id(name: str) -> int:
    """A parameter's ID.

    Args:
        name: `<instance>.<parameter>`.

    Returns:
        Its ID.
    """
    return next(i for i, p in DICTIONARY.parameters_by_id.items() if p.name == name)


def test_a_case_s_file_boots_every_parameter_valid(
    fsw: ModuleType, prm_record: Path, prm: str, parameter_ids: list[int]
):
    """The case's record holds every parameter of the deployment, and booted on it the copy steps.

    Args:
        fsw: the test's copy.
        prm_record: the case's parameter record.
        prm: the case's parameter file.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    recorded = {
        f"{instance.rsplit('.', 1)[1]}.{name}"
        for instance, values in json.loads(prm_record.read_text()).items()
        for name in values
    }
    assert recorded == {p.name for p in DICTIONARY.parameters_by_id.values()}

    fsw.boot(prm, parameter_ids)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert fsw.telemetry()


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


def test_a_file_whose_crc_fails_fails_the_boot(fsw: ModuleType, prm: str, parameter_ids: list[int]):
    """A byte changed after the CRC was written leaves every parameter invalid.

    Args:
        fsw: the test's copy.
        prm: the case's parameter file, corrupted here.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    dat = Path(prm)
    data = bytearray(dat.read_bytes())
    data[-1] ^= 0xFF
    dat.write_bytes(bytes(data))

    with pytest.raises(RuntimeError, match="are not valid"):
        fsw.boot(prm, parameter_ids)


def test_a_file_that_is_not_a_parameter_file_fails_the_boot(
    fsw: ModuleType, tmp_path: Path, parameter_ids: list[int]
):
    """Bytes that are not F´'s parameter format leave every parameter invalid.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    dat = tmp_path / "run_0000.prm.dat"
    dat.write_bytes(b"not a parameter file")

    with pytest.raises(RuntimeError, match="are not valid"):
        fsw.boot(str(dat), parameter_ids)


def test_a_parameter_missing_from_the_record_fails_the_boot(
    fsw: ModuleType, prm_record: Path, parameter_ids: list[int]
):
    """A record without one parameter makes a `.dat` without it; boot names that parameter alone.

    Args:
        fsw: the test's copy.
        prm_record: the case's parameter record, edited here.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    entries = json.loads(prm_record.read_text())
    instance, values = next(iter(entries.items()))
    parameter = next(iter(values))
    del values[parameter]
    prm_record.write_text(json.dumps(entries))
    dropped = _id(f"{instance.rsplit('.', 1)[1]}.{parameter}")

    with pytest.raises(RuntimeError, match=rf"^parameters {dropped} are not valid"):
        fsw.boot(str(parameters.dat(prm_record, DICTIONARY_PATH)), parameter_ids)


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
    station: FprimeStation,
    tmp_path: Path,
    prm_record: Path,
    parameter_ids: list[int],
):
    """Every value edited in the record is the one PrmDb holds, read back from its own image.

    The `.dat` is removed once booted, so the file decoded is the one `PRM_SAVE_FILE` writes.
    F´'s `fprime-prm-decode` is always given `-o`, since it would otherwise overwrite the record.

    Args:
        fsw: the test's copy.
        station: the station on it.
        tmp_path: where PrmDb's image is decoded.
        prm_record: the case's parameter record, edited here.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    entries = json.loads(prm_record.read_text())
    counter = itertools.count(1)
    edited = {
        instance: {name: _changed(value, counter) for name, value in values.items()}
        for instance, values in entries.items()
    }
    assert edited != entries
    prm_record.write_text(json.dumps(edited))
    dat = parameters.dat(prm_record, DICTIONARY_PATH)
    fsw.boot(str(dat), parameter_ids)
    dat.unlink()

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 1)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))
    decoded = tmp_path / "decoded.json"
    tool = Path(sys.executable).parent / "fprime-prm-decode"
    command = [tool, dat, "-d", DICTIONARY_PATH, "-o", decoded]
    subprocess.run(command, check=True, capture_output=True)

    assert station.responses() == [(1, "OK", None)]
    assert json.loads(decoded.read_text()) == edited


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


@pytest.mark.parametrize(("length", "boots"), [(239, True), (240, False)])
def test_a_file_s_path_fits_f_prime_s_file_names_up_to_239_characters(
    fsw: ModuleType, tmp_path: Path, prm: str, parameter_ids: list[int], length: int, boots: bool
):
    """F´'s 240-character file names hold a path of 239; one of 240 cannot be read.

    Args:
        fsw: the test's copy.
        tmp_path: where the path is made.
        prm: the case's parameter file, copied to the path.
        parameter_ids: every parameter's ID, which boot holds valid.
        length: the path's length in characters.
        boots: whether the copy boots on it.
    """
    path = _of_length(tmp_path, length, "x")
    shutil.copyfile(prm, path)

    if boots:
        fsw.boot(str(path), parameter_ids)
    else:
        with pytest.raises(RuntimeError, match="are not valid"):
            fsw.boot(str(path), parameter_ids)


def test_a_case_directory_of_239_characters_trips_f_prime_s_assert(
    fsw: ModuleType, tmp_path: Path, prm: str, parameter_ids: list[int]
):
    """A sandbox directory of 239 characters is past what F´'s sandbox holds, and asserts.

    Args:
        fsw: the test's copy.
        tmp_path: where the case's directory is made.
        prm: the case's parameter file, copied into that directory.
        parameter_ids: every parameter's ID, which boot holds valid.
    """
    directory = _of_length(tmp_path, 239, "d")
    directory.mkdir()
    shutil.copyfile(prm, directory / "a")

    with pytest.raises(RuntimeError, match=r'^Assert: ".*SandboxedFile\.cpp:\d+"'):
        fsw.boot(str(directory / "a"), parameter_ids)


def _load_file(station: FprimeStation, path: Path) -> bytes:
    """`prmDb.PRM_LOAD_FILE`'s packet, merging, its string argument serialized by hand.

    The station codes no string argument, so the packet is built here: the header the station
    gives a command, then F´'s string, its length as `FwSizeStoreType` before its bytes, then the
    merge enumeration's `MERGE`. A command's string holds at most `FW_CMD_STRING_MAX_SIZE`, 40
    characters, so the path is a short relative one.

    Args:
        station: the station on the copy.
        path: the file to load, relative to the working directory.

    Returns:
        The packet.
    """
    command = DICTIONARY.command("prmDb.PRM_LOAD_FILE")
    header = station.encode_command("prmDb.PRM_SAVE_FILE", {})
    header = header[: -DICTIONARY.type("FwOpcodeType").dtype.itemsize]
    header += DICTIONARY.type("FwOpcodeType").serialized([command.opcode]).tobytes()
    name = str(path).encode()
    size = DICTIONARY.type("FwSizeStoreType").serialized([len(name)]).tobytes()
    return header + size + name + bytes([0])


def test_the_sandbox_is_the_case_s_directory(
    fsw: ModuleType,
    tmp_path: Path,
    prm: str,
    parameter_ids: list[int],
    monkeypatch: pytest.MonkeyPatch,
):
    """PrmDb saves to the case's file and loads one beside it, but none from another directory.

    Args:
        fsw: the test's copy.
        tmp_path: the test's directory, holding the case's directory `case` and `elsewhere`.
        prm: the case's parameter file, in `case`.
        parameter_ids: every parameter's ID, which boot holds valid.
        monkeypatch: sets the working directory, which the loaded paths are relative to.
    """
    monkeypatch.chdir(tmp_path)
    dat = Path(prm)
    case, elsewhere = dat.parent, tmp_path / "elsewhere"
    assert case == tmp_path / "case"
    elsewhere.mkdir()
    shutil.copyfile(dat, case / "beside.dat")
    shutil.copyfile(dat, elsewhere / "outside.dat")
    station = FprimeStation(fsw, DICTIONARY)
    fsw.boot(prm, parameter_ids)
    dat.unlink()

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 1)
    fsw.uplink(_load_file(station, Path("elsewhere/outside.dat")), 2)
    fsw.uplink(_load_file(station, Path("case/beside.dat")), 3)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert station.responses() == [(1, "OK", None), (2, "EXECUTION_ERROR", None), (3, "OK", None)]
    assert dat.exists()
