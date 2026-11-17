"""The bus emulator: a Basilisk message as the bytes a vehicle's bus carries, built from Bus.fpp.

Each bus struct in `fsw/fpp/interfaces/Bus.fpp`, `Bus.<Name>`, mirrors the Basilisk payload
`messaging.<Name>Payload`, matched ignoring case as `fsw/fpp/interfaces/bus_test.py` holds them.
`serialize` writes a payload as F´ serializes its bus struct: each member in declaration order,
big-endian, packed and unframed. It is built from `Bus.fpp` at import, read alone, so no file is
generated and no F´ framework clone is read; each payload type's packer is planned on its first
message, and a member outside `fsw.codegen.fields.STRUCT_CODES` raises then. Lab equipment: a real
vehicle's bus delivers the bytes itself, and the Python build reads messages without them.
"""

import functools
import struct
from pathlib import Path
from typing import Any

from Basilisk.architecture import messaging

from fsw.codegen.fields import STRUCT_CODES
from fsw.codegen.fpp_model import Struct, read

__all__ = ["BUS", "serialize"]

BUS = Path(__file__).resolve().parents[1] / "fsw" / "fpp" / "interfaces" / "Bus.fpp"
"""The bus structs' FPP file."""

_STRUCTS = {
    name.removeprefix("Bus.").lower() + "payload": struct_
    for name, struct_ in read([BUS]).types.items()
    if name.startswith("Bus.") and isinstance(struct_, Struct)
}
"""Each bus struct, by the name of the payload it mirrors in lower case."""


@functools.cache
def _packer(payload: type) -> tuple[struct.Struct, tuple[str, ...]]:
    """A payload type's packer, and its fields in the bus struct's order, planned once.

    Args:
        payload: `messaging`'s payload class.

    Returns:
        The packer, and the payload's name for each bus member.

    Raises:
        KeyError: no bus struct mirrors the payload, naming it; or a member is not an inline array
            of one of `fsw.codegen.fields.STRUCT_CODES`, naming the member and the type.
    """
    key = payload.__name__.lower()
    if key not in _STRUCTS:
        raise KeyError(f"no bus struct in {BUS.name} mirrors {payload.__name__}")
    bus = _STRUCTS[key]
    fields = {name.lower(): name for name in payload.__dtype__.names}
    layout = ">"
    for member in bus.members:
        if member.type not in STRUCT_CODES or member.size is None:
            size = "" if member.size is None else f"[{member.size}] "
            raise KeyError(
                f"{bus.name}.{member.name} is {size}{member.type}, which the bus emulator does not"
                " write: it writes inline arrays of fsw.codegen.fields.STRUCT_CODES' primitives"
            )
        layout += f"{member.size}{STRUCT_CODES[member.type]}"
    return struct.Struct(layout), tuple(fields[member.name.lower()] for member in bus.members)


def serialize(message: Any) -> bytes:
    """A Basilisk message's bytes, as F´ serializes the bus struct that mirrors it.

    A message no bus struct mirrors, or whose bus struct has a member outside
    `fsw.codegen.fields.STRUCT_CODES`, raises `KeyError` naming it.

    Args:
        message: the message's payload. Its class is resolved by its name in `messaging`, since
            SWIG can return another module's class of that name.

    Returns:
        The bytes.
    """
    packer, fields = _packer(getattr(messaging, type(message).__name__))
    return packer.pack(*(value for field in fields for value in getattr(message, field)))
