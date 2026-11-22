"""Each bus struct in `Bus.fpp` mirrors the Basilisk message payload of its name.

`Bus.<Name>` is held to `messaging.<Name>Payload`: its members' names, element types and shapes, in
order, equal the fields of the payload's `__dtype__`. Every name, struct's and member's alike, is
matched ignoring case. Offsets and padding are not compared, since F´ serializes packed. Reads
`Bus.fpp` alone through the native `fpp to-json`, so it needs neither the F´ framework clone nor an
F´ build.
"""

import re
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.fields import DTYPES
from fsw.codegen.fpp_model import Struct, read
from fsw.payloads import payload_type

BUS = Path(__file__).with_name("Bus.fpp")

Field = tuple[str, np.dtype]
"""A field's name in lower case, and its numpy type: element type and shape."""


def _bus_structs(path: Path) -> list[Struct]:
    """Every struct of module `Bus` in an FPP file.

    Args:
        path: the `.fpp` file.

    Returns:
        The structs.
    """
    types = read([path]).types
    return [t for name, t in types.items() if name.startswith("Bus.") and isinstance(t, Struct)]


def _struct_fields(struct: Struct) -> list[Field]:
    """A bus struct's members, as fields.

    Args:
        struct: the bus struct.

    Returns:
        Its members, in FPP's order.

    Raises:
        KeyError: a member's element type has no numpy type in `fsw.codegen.fields.DTYPES`,
            naming the type.
    """
    fields = []
    for member in struct.members:
        if member.type not in DTYPES:
            raise KeyError(f"{struct.name}.{member.name}: no numpy type for {member.type}")
        shape = () if member.size is None else (member.size,)
        fields.append((member.name.lower(), np.dtype((DTYPES[member.type], shape))))
    return fields


def _payload_fields(struct: Struct) -> list[Field]:
    """The fields of the Basilisk payload a bus struct mirrors.

    Args:
        struct: the bus struct, `Bus.<Name>`.

    Returns:
        The fields of `messaging.<Name>Payload`, in Basilisk's order.
    """
    dtype = payload_type(struct.name).__dtype__
    return [(n.lower(), dtype.fields[n][0]) for n in dtype.names]


def test_each_bus_struct_mirrors_its_basilisk_payload() -> None:
    """Every bus struct's members are its payload's fields: names, types and shapes, in order."""
    structs = _bus_structs(BUS)
    assert structs
    for struct in structs:
        assert _struct_fields(struct) == _payload_fields(struct), struct.name


Seed = Callable[[list[str], list[int]], None]
"""A drift seeded into a struct's member lines: the file's lines, and the indices of the struct's
members' lines, in FPP's order."""


def _rename(lines: list[str], members: list[int]) -> None:
    """The first member renamed.

    Args:
        lines: Bus.fpp's lines, edited in place.
        members: the indices of the struct's members' lines.
    """
    lines[members[0]] = lines[members[0]].replace(":", "Renamed:", 1)


def _delete(lines: list[str], members: list[int]) -> None:
    """The first member deleted.

    Args:
        lines: Bus.fpp's lines, edited in place.
        members: the indices of the struct's members' lines.
    """
    lines[members[0]] = ""


def _swap(lines: list[str], members: list[int]) -> None:
    """The first two members in each other's place.

    Args:
        lines: Bus.fpp's lines, edited in place.
        members: the indices of the struct's members' lines.
    """
    first, second = members[:2]
    lines[first], lines[second] = lines[second], lines[first]


def _reshape(lines: list[str], members: list[int]) -> None:
    """The first array member one element longer.

    Args:
        lines: Bus.fpp's lines, edited in place.
        members: the indices of the struct's members' lines.
    """
    index = next(i for i in members if re.search(r":\s*\[\d+\]", lines[i]))
    lines[index] = re.sub(
        r"\[(\d+)\]", lambda size: f"[{int(size.group(1)) + 1}]", lines[index], count=1
    )


def _recase(lines: list[str], members: list[int]) -> None:
    """The first member's name in capitals, a name that differs only in case.

    Args:
        lines: Bus.fpp's lines, edited in place.
        members: the indices of the struct's members' lines.
    """
    name, rest = lines[members[0]].split(":", 1)
    lines[members[0]] = f"{name.upper()}:{rest}"


def _seeded(struct: Struct, seed: Seed, tmp_path: Path) -> Struct:
    """A bus struct from a copy of Bus.fpp with a drift seeded into it, once seen to change it.

    Args:
        struct: the struct, as Bus.fpp declares it.
        seed: the drift to seed into the struct's member lines.
        tmp_path: where the copy is written.

    Returns:
        The copy's struct of that name.
    """
    text = BUS.read_text()
    lines = text.splitlines(keepends=True)
    opening = re.compile(rf"\s*struct {re.escape(struct.name.removeprefix('Bus.'))}\s*\{{")
    start = next(i for i, line in enumerate(lines) if opening.match(line))
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "}")
    names = {member.name for member in struct.members}
    members = [i for i in range(start + 1, end) if lines[i].split(":", 1)[0].strip() in names]
    assert len(members) == len(struct.members), struct.name
    seed(lines, members)
    seeded = "".join(lines)
    assert seeded != text
    copy = tmp_path / "Bus.fpp"
    copy.write_text(seeded)
    (copied,) = (s for s in _bus_structs(copy) if s.name == struct.name)
    return copied


STRUCTS = _bus_structs(BUS)
"""Every bus struct Bus.fpp declares."""


@pytest.mark.parametrize("struct", STRUCTS, ids=lambda struct: struct.name)
@pytest.mark.parametrize(
    "seed", [_rename, _delete, _swap, _reshape], ids=["renamed", "missing", "swapped", "reshaped"]
)
def test_a_drifted_bus_struct_differs_from_its_payload(
    struct: Struct, seed: Seed, tmp_path: Path
) -> None:
    """A copy of Bus.fpp with a member renamed, missing, moved or resized no longer mirrors it.

    Args:
        struct: the bus struct the drift is seeded into.
        seed: the drift.
        tmp_path: where the seeded copy is written.
    """
    if seed is _swap and len(struct.members) < 2:
        pytest.skip(f"{struct.name} has one member, so none can move")
    if seed is _reshape and all(member.size is None for member in struct.members):
        pytest.skip(f"{struct.name} has no array member to resize")
    drifted = _seeded(struct, seed, tmp_path)
    assert _struct_fields(drifted) != _payload_fields(drifted)


@pytest.mark.parametrize("struct", STRUCTS, ids=lambda struct: struct.name)
def test_a_member_name_differing_only_in_case_still_mirrors_its_field(
    struct: Struct, tmp_path: Path
) -> None:
    """A copy of Bus.fpp with a member's name in capitals still mirrors its payload.

    Args:
        struct: the bus struct the recased name is seeded into.
        tmp_path: where the seeded copy is written.
    """
    recased = _seeded(struct, _recase, tmp_path)
    assert _struct_fields(recased) == _payload_fields(recased)
