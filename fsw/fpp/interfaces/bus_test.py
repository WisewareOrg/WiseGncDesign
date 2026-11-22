"""Each bus struct in `Bus.fpp` mirrors the Basilisk message payload of its name.

`Bus.<Name>` is held to `messaging.<Name>Payload`: its members' names, element types and shapes, in
order, equal the fields of the payload's `__dtype__`. Every name, struct's and member's alike, is
matched ignoring case. Offsets and padding are not compared, since F´ serializes packed. Reads
`Bus.fpp` alone through the native `fpp to-json`, so it needs neither the F´ framework clone nor an
F´ build.
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from fsw.codegen.fields import DTYPES
from fsw.codegen.fpp_model import Member, Struct, read
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


Edit = Callable[[tuple[Member, ...]], tuple[Member, ...]]
"""An edit of a struct's members."""


def _rename(members: tuple[Member, ...]) -> tuple[Member, ...]:
    """The first member renamed.

    Args:
        members: the struct's members.

    Returns:
        The members.
    """
    return (members[0]._replace(name=members[0].name + "Renamed"), *members[1:])


def _delete(members: tuple[Member, ...]) -> tuple[Member, ...]:
    """The first member deleted.

    Args:
        members: the struct's members.

    Returns:
        The members.
    """
    return members[1:]


def _swap(members: tuple[Member, ...]) -> tuple[Member, ...]:
    """The first two members in each other's place.

    Args:
        members: the struct's members.

    Returns:
        The members.
    """
    return (members[1], members[0], *members[2:])


def _reshape(members: tuple[Member, ...]) -> tuple[Member, ...]:
    """The first array member one element longer.

    Args:
        members: the struct's members.

    Returns:
        The members.
    """
    index = next(i for i, member in enumerate(members) if member.size is not None)
    size = members[index].size
    assert size is not None, "the member is an array"
    longer = members[index]._replace(size=size + 1)
    return (*members[:index], longer, *members[index + 1 :])


def _recase(members: tuple[Member, ...]) -> tuple[Member, ...]:
    """The first member's name in capitals, a name that differs only in case.

    Args:
        members: the struct's members.

    Returns:
        The members.
    """
    return (members[0]._replace(name=members[0].name.upper()), *members[1:])


STRUCTS = _bus_structs(BUS)
"""Every bus struct Bus.fpp declares."""


@pytest.mark.parametrize("struct", STRUCTS, ids=lambda struct: struct.name)
@pytest.mark.parametrize(
    ("edit", "mirrors"),
    [(_rename, False), (_delete, False), (_swap, False), (_reshape, False), (_recase, True)],
    ids=["renamed", "missing", "swapped", "reshaped", "recased"],
)
def test_an_edited_bus_struct_mirrors_its_payload_only_when_the_edit_is_in_case_alone(
    struct: Struct, edit: Edit, mirrors: bool
) -> None:
    """A member renamed, missing, moved or resized no longer mirrors the payload; a recase does.

    Each struct is edited in memory, and held to the payload of the unedited struct.

    Args:
        struct: the bus struct, edited.
        edit: the edit.
        mirrors: whether the edited struct still mirrors its payload.
    """
    if edit is _swap and len(struct.members) < 2:
        pytest.skip(f"{struct.name} has one member, so none can move")
    if edit is _reshape and all(member.size is None for member in struct.members):
        pytest.skip(f"{struct.name} has no array member to resize")
    edited = struct._replace(members=edit(struct.members))
    assert (_struct_fields(edited) == _payload_fields(struct)) is mirrors
