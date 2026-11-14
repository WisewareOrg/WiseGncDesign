"""Each bus struct in `Bus.fpp` mirrors the Basilisk message payload of its name.

`Bus.<Name>` is held to `messaging.<Name>Payload`, the name matched ignoring case: its members'
names, ignoring case, element types and shapes, in order, equal the payload's fields in Basilisk's
`__dtype__`. Offsets and padding are not compared, since F´ serializes packed. Reads `Bus.fpp` alone
through the native `fpp to-json`, so it needs neither the F´ framework clone nor an F´ build.
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fpp_model import Struct, read

BUS = Path(__file__).with_name("Bus.fpp")

_DTYPES = {"F64": np.dtype("float64")}
"""Each FPP element type a bus struct uses, as Basilisk's numpy type."""

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
        KeyError: a member's element type has no numpy type in `_DTYPES`, naming the type.
    """
    fields = []
    for member in struct.members:
        if member.type not in _DTYPES:
            raise KeyError(f"{struct.name}.{member.name}: no numpy type for {member.type}")
        shape = () if member.size is None else (member.size,)
        fields.append((member.name.lower(), np.dtype((_DTYPES[member.type], shape))))
    return fields


def _payload_fields(struct: Struct) -> list[Field]:
    """The fields of the Basilisk payload a bus struct mirrors.

    Args:
        struct: the bus struct, `Bus.<Name>`.

    Returns:
        The fields of `messaging.<Name>Payload`, the name matched ignoring case, in Basilisk's
        order.

    Raises:
        KeyError: no payload matches the struct's name.
    """
    wanted = struct.name.removeprefix("Bus.").lower() + "payload"
    payloads = {n.lower(): getattr(messaging, n) for n in dir(messaging) if n.endswith("Payload")}
    if wanted not in payloads:
        raise KeyError(f"{struct.name}: no Basilisk payload named like {wanted}")
    dtype = payloads[wanted].__dtype__
    return [(n.lower(), dtype.fields[n][0]) for n in dtype.names]


def test_each_bus_struct_mirrors_its_basilisk_payload() -> None:
    """Every bus struct's members are its payload's fields: names, types and shapes, in order."""
    structs = _bus_structs(BUS)
    assert structs
    for struct in structs:
        assert _struct_fields(struct) == _payload_fields(struct), struct.name


def _rename(text: str) -> str:
    """Bus.fpp with `angVelPlatform` renamed.

    Args:
        text: Bus.fpp's text.

    Returns:
        The seeded text.
    """
    return text.replace("angVelPlatform:", "angularVelocityPlatform:")


def _delete(text: str) -> str:
    """Bus.fpp with `drFramePlatform` deleted.

    Args:
        text: Bus.fpp's text.

    Returns:
        The seeded text.
    """
    lines = text.splitlines(keepends=True)
    return "".join(line for line in lines if not line.strip().startswith("drFramePlatform:"))


@pytest.mark.parametrize("seed", [_rename, _delete], ids=["renamed", "missing"])
def test_a_drifted_bus_struct_differs_from_its_payload(
    seed: Callable[[str], str], tmp_path: Path
) -> None:
    """A copy of Bus.fpp with a member renamed, or a Basilisk field missing, no longer mirrors it.

    Args:
        seed: the drift to seed into the copy.
        tmp_path: where the seeded copy is written.
    """
    text = BUS.read_text()
    seeded = seed(text)
    assert seeded != text
    copy = tmp_path / "Bus.fpp"
    copy.write_text(seeded)
    (struct,) = (s for s in _bus_structs(copy) if s.name == "Bus.ImuSensorMsg")
    assert _struct_fields(struct) != _payload_fields(struct)
