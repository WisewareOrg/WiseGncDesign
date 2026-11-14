"""The pin's boot: PrmDb loads the case's parameter file, and a parameter left invalid fails it.

Skipped without the deployment `just fsw` builds.
"""

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from fsw.codegen.fpp_types import Gnc
from ground import parameters
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY as DICTIONARY_PATH
from lab.power_cycle import power_cycle

if importlib.util.find_spec("lab._wise_fsw") is None:
    pytest.skip("the F´ build is absent; run `just fsw`", allow_module_level=True)

DICTIONARY = Dictionary(DICTIONARY_PATH)
"""The deployment's dictionary, which the build generated."""

IDS = sorted(DICTIONARY.parameters_by_id)
"""Every parameter's ID."""

NAV = Gnc.ImuDeadReckonerParameters(mu=3.986004360e14, dcm_PB=np.eye(3))
"""Nav's parameters: Earth's mu and an identity mounting."""

NS = 1_000_000_000
"""ns per s."""


def _case(directory: Path, nav: tuple = NAV) -> Path:
    """Writes a case's parameter record and makes its `.dat` beside it.

    Args:
        directory: the case's directory.
        nav: nav's parameters.

    Returns:
        The `.dat`.
    """
    return parameters.dat(parameters.write(nav, directory / "run_0000.prm.json"), DICTIONARY_PATH)


def _id(name: str) -> int:
    """A parameter's ID.

    Args:
        name: `<instance>.<parameter>`.

    Returns:
        Its ID.
    """
    return next(i for i, p in DICTIONARY.parameters_by_id.items() if p.name == name)


@pytest.fixture
def fsw() -> ModuleType:
    """A fresh copy of the deployment, not yet booted.

    Returns:
        The copy.
    """
    return power_cycle()


def test_a_case_s_file_boots_every_parameter_valid(fsw: ModuleType, tmp_path: Path):
    """Booted on a file with every parameter, the copy steps.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
    """
    assert sorted([_id("nav.mu"), _id("nav.dcm_PB")]) == IDS

    fsw.boot(str(_case(tmp_path)), IDS)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert fsw.telemetry()


def test_a_missing_file_fails_the_boot(fsw: ModuleType, tmp_path: Path):
    """No file at the path leaves every parameter invalid, each named.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
    """
    missing = tmp_path / "run_0000.prm.dat"

    with pytest.raises(RuntimeError, match=f"parameters {IDS[0]}, {IDS[1]} are not valid"):
        fsw.boot(str(missing), IDS)


def test_a_file_whose_crc_fails_fails_the_boot(fsw: ModuleType, tmp_path: Path):
    """A byte changed after the CRC was written leaves every parameter invalid.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
    """
    dat = _case(tmp_path)
    data = bytearray(dat.read_bytes())
    data[-1] ^= 0xFF
    dat.write_bytes(bytes(data))

    with pytest.raises(RuntimeError, match="are not valid"):
        fsw.boot(str(dat), IDS)


def test_a_file_that_is_not_a_parameter_file_fails_the_boot(fsw: ModuleType, tmp_path: Path):
    """Bytes that are not F´'s parameter format leave every parameter invalid.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
    """
    dat = tmp_path / "run_0000.prm.dat"
    dat.write_bytes(b"not a parameter file")

    with pytest.raises(RuntimeError, match="are not valid"):
        fsw.boot(str(dat), IDS)


def test_a_parameter_missing_from_the_record_fails_the_boot(fsw: ModuleType, tmp_path: Path):
    """A record without `dcm_PB` makes a `.dat` without it; boot names that parameter alone.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
    """
    record = parameters.write(NAV, tmp_path / "run_0000.prm.json")
    entries = json.loads(record.read_text())
    (nav,) = entries.values()
    del nav["dcm_PB"]
    record.write_text(json.dumps(entries))

    with pytest.raises(RuntimeError, match=rf"^parameters {_id('nav.dcm_PB')} are not valid"):
        fsw.boot(str(parameters.dat(record, DICTIONARY_PATH)), IDS)


@pytest.mark.parametrize("path", ["run_0000.prm.dat", "/run_0000.prm.dat"])
def test_a_relative_path_or_one_in_the_root_is_refused(fsw: ModuleType, path: str):
    """The sandbox is the file's directory, which is never the root, so neither path boots.

    Args:
        fsw: the test's copy.
        path: the parameter file's path.
    """
    with pytest.raises(ValueError, match="not an absolute path in a directory below the root"):
        fsw.boot(path, IDS)


def test_a_path_longer_than_f_prime_s_file_names_fails_the_boot(fsw: ModuleType, tmp_path: Path):
    """A path past F´'s 240-character file names cannot be read, so the boot fails.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
    """
    dat = _case(tmp_path)
    long = dat.with_name("x" * (250 - len(str(tmp_path))) + ".dat")
    shutil.copyfile(dat, long)
    assert len(str(long)) > 240

    with pytest.raises(RuntimeError, match="are not valid"):
        fsw.boot(str(long), IDS)


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
    fsw: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """PrmDb saves to the case's file and loads one beside it, but none from another directory.

    Args:
        fsw: the test's copy.
        tmp_path: the case's directory.
        monkeypatch: sets the working directory, which the loaded paths are relative to.
    """
    monkeypatch.chdir(tmp_path)
    case, elsewhere = tmp_path / "case", tmp_path / "elsewhere"
    case.mkdir()
    elsewhere.mkdir()
    dat = _case(case)
    shutil.copyfile(dat, case / "beside.dat")
    shutil.copyfile(dat, elsewhere / "outside.dat")
    station = FprimeStation(fsw, DICTIONARY)
    fsw.boot(str(dat), IDS)
    dat.unlink()

    station.uplink("prmDb.PRM_SAVE_FILE", {}, 1)
    fsw.uplink(_load_file(station, Path("elsewhere/outside.dat")), 2)
    fsw.uplink(_load_file(station, Path("case/beside.dat")), 3)
    fsw.step(t_ns=NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    assert station.responses() == [(1, "OK", None), (2, "EXECUTION_ERROR", None), (3, "OK", None)]
    assert dat.exists()
