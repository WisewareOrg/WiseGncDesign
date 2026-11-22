"""The bus emulator: a Basilisk message as the bytes a vehicle's bus carries, and back, by Bus.fpp.

Each bus struct in `fsw/fpp/interfaces/Bus.fpp`, `Bus.<Name>`, mirrors the Basilisk payload
`fsw.payloads.payload_type` gives. `serialize` writes a payload as F´ serializes its bus struct:
each member in declaration order, big-endian, packed and unframed. It is built from `Bus.fpp` at
import, read alone, so no file is generated and no F´ framework clone is read; each payload type's
packer is planned on its first message, and a member outside `fsw.codegen.fields.STRUCT_CODES`
raises then. `deserialize` reads an actuator's bytes back with the same packer, into a fresh
payload. Lab equipment: a real vehicle's bus carries the bytes itself, and the Python build reads
and writes messages without them.
"""

import functools
import struct
from pathlib import Path
from typing import Any

from Basilisk.architecture import messaging

from fsw.codegen.fields import STRUCT_CODES
from fsw.codegen.fpp_model import Struct, read
from fsw.payloads import Payload, payload_type

__all__ = ["BUS", "deserialize", "serialize"]

BUS = Path(__file__).resolve().parents[1] / "fsw" / "fpp" / "interfaces" / "Bus.fpp"
"""The bus structs' FPP file."""

_STRUCTS = {
    payload_type(name): struct_
    for name, struct_ in read([BUS]).types.items()
    if name.startswith("Bus.") and isinstance(struct_, Struct)
}
"""Each bus struct, by the Basilisk payload class it mirrors."""


@functools.cache
def _packer(payload: type[Payload]) -> tuple[struct.Struct, tuple[str, ...]]:
    """A payload type's packer, and its fields in the bus struct's order, planned once.

    Args:
        payload: `messaging`'s payload class.

    Returns:
        The packer, and the payload's name for each bus member.

    Raises:
        KeyError: no bus struct mirrors the payload, naming it; or a member is not an inline array
            of one of `fsw.codegen.fields.STRUCT_CODES`, naming the member and the type.
    """
    if payload not in _STRUCTS:
        raise KeyError(f"no bus struct in {BUS.name} mirrors {payload.__name__}")
    bus = _STRUCTS[payload]
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


def deserialize(bus: str, data: bytes) -> Any:
    """A bus struct's bytes, as F´ serializes it, as a fresh payload of the message it mirrors.

    Bytes of another length than the struct's raise `struct.error`; a struct with a member outside
    `fsw.codegen.fields.STRUCT_CODES` raises `KeyError`, naming it.

    Args:
        bus: the bus struct's qualified name, `Bus.<Name>`.
        data: the bytes.

    Returns:
        The payload class the struct mirrors, by `fsw.payloads.payload_type`, each field set from
        its member's elements.
    """
    payload = payload_type(bus)()
    packer, fields = _packer(type(payload))
    values = iter(packer.unpack(data))
    for member, field in zip(_STRUCTS[type(payload)].members, fields, strict=True):
        assert member.size is not None, f"{member.name} is an array"
        setattr(payload, field, [next(values) for _ in range(member.size)])
    return payload
