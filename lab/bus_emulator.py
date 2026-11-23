"""The bus emulator: a Basilisk message as the bytes a vehicle's bus carries, and back, by Bus.fpp.

Each bus struct in `fsw/fpp/interfaces/Bus.fpp`, `Bus.<Name>`, mirrors the Basilisk payload
`fsw.payloads.payload_type` gives. Its bytes are F´'s serialization of the struct: each member in
declaration order, big-endian, packed and unframed. A payload type's copy is planned once, from
`Bus.fpp` read alone at import, as runs of elements cast between the payload's C struct and the
bus bytes, a run per stretch of members contiguous and of one type in both; a member outside
`fsw.codegen.fields.STRUCT_CODES` raises then. `to_bus` and `from_bus` bind a payload's memory to a
buffer once, so each copy after is the planned casts alone; `serialize` and `deserialize` are the
same copies into fresh bytes and a fresh payload. Lab equipment: a real vehicle's bus carries the
bytes itself, and the Python build reads and writes messages without them.
"""

import ctypes
import functools
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
from Basilisk.architecture import messaging

from fsw.codegen.fields import DTYPES, STRUCT_CODES
from fsw.codegen.fpp_model import Struct, read
from fsw.payloads import Payload, payload_type

__all__ = ["BUS", "deserialize", "from_bus", "serialize", "size", "to_bus"]

BUS = Path(__file__).resolve().parents[1] / "fsw" / "fpp" / "interfaces" / "Bus.fpp"
"""The bus structs' FPP file."""

_STRUCTS = {
    payload_type(name): struct_
    for name, struct_ in read([BUS]).types.items()
    if name.startswith("Bus.") and isinstance(struct_, Struct)
}
"""Each bus struct, by the Basilisk payload class it mirrors."""


class _Run(NamedTuple):
    """Elements of one type, contiguous in the payload's C struct and in the bus bytes.

    Attributes:
        payload: the run's first byte in the payload's C struct.
        bus: the run's first byte in the bus bytes.
        count: its elements.
        dtype: its elements' type, native byte order.
    """

    payload: int
    bus: int
    count: int
    dtype: np.dtype


class _Plan(NamedTuple):
    """A payload type's copy to and from its bus bytes.

    Attributes:
        size: the bus bytes' length.
        runs: the runs, in bus order.
    """

    size: int
    runs: tuple[_Run, ...]


@functools.cache
def _plan(payload: type[Payload]) -> _Plan:
    """A payload type's copy, planned once.

    Args:
        payload: `messaging`'s payload class.

    Returns:
        The plan.

    Raises:
        KeyError: no bus struct mirrors the payload, naming it; or a member is not an inline array
            of one of `fsw.codegen.fields.STRUCT_CODES`, naming the member and the type.
    """
    if payload not in _STRUCTS:
        raise KeyError(f"no bus struct in {BUS.name} mirrors {payload.__name__}")
    bus = _STRUCTS[payload]
    fields = {name.lower(): name for name in payload.__dtype__.names}
    runs: list[_Run] = []
    offset = 0
    for member in bus.members:
        if member.type not in STRUCT_CODES or member.size is None:
            size = "" if member.size is None else f"[{member.size}] "
            raise KeyError(
                f"{bus.name}.{member.name} is {size}{member.type}, which the bus emulator does not"
                " write: it writes inline arrays of fsw.codegen.fields.STRUCT_CODES' primitives"
            )
        dtype = DTYPES[member.type]
        source = payload.__dtype__.fields[fields[member.name.lower()]][1]
        last = runs[-1] if runs else None
        if last and last.dtype == dtype and last.payload + last.count * dtype.itemsize == source:
            runs[-1] = last._replace(count=last.count + member.size)
        else:
            runs.append(_Run(source, offset, member.size, dtype))
        offset += member.size * dtype.itemsize
    return _Plan(offset, tuple(runs))


def _payload_class(payload: Any) -> type[Payload]:
    """A payload's class in `messaging`, since SWIG can return another module's class of its name.

    Args:
        payload: the payload.

    Returns:
        The class.
    """
    return getattr(messaging, type(payload).__name__)


def _pairs(payload: Any, buffer: Any) -> list[tuple[np.ndarray, np.ndarray]]:
    """Each run's view of a payload's C struct and of a buffer, in native and bus byte order.

    Args:
        payload: the payload, a SWIG proxy whose `this` is its C struct's address.
        buffer: the bus bytes, as long as the struct's.

    Returns:
        `(payload view, bus view)` per run.

    Raises:
        ValueError: the buffer is not the bus struct's length, naming both.
    """
    payload_class = _payload_class(payload)
    plan = _plan(payload_class)
    memory = np.frombuffer((ctypes.c_char * payload_class.__dtype__.itemsize).from_address(int(payload.this)), np.uint8)
    bus = np.frombuffer(buffer, np.uint8)
    if bus.size != plan.size:
        raise ValueError(f"{_STRUCTS[payload_class].name} is {plan.size} bytes on the bus, not {bus.size}")
    width = [run.count * run.dtype.itemsize for run in plan.runs]
    return [
        (
            memory[run.payload : run.payload + n].view(run.dtype),
            bus[run.bus : run.bus + n].view(run.dtype.newbyteorder(">")),
        )
        for run, n in zip(plan.runs, width, strict=True)
    ]


def size(bus: str) -> int:
    """A bus struct's length on the bus.

    Args:
        bus: the bus struct's qualified name, `Bus.<Name>`.

    Returns:
        Its bytes.
    """
    return _plan(payload_type(bus)).size


def to_bus(payload: Any, buffer: Any) -> Callable[[], None]:
    """Binds a payload to the buffer its bus bytes go to.

    Args:
        payload: the message's payload, which must outlive the copy.
        buffer: a writable buffer of the bus struct's length.

    Returns:
        The copy: each call writes the payload's values, as they stand, into the buffer.
    """
    pairs = [(bus, memory) for memory, bus in _pairs(payload, buffer)]

    def copy() -> None:
        """Writes the payload's values into the buffer."""
        for bus, memory in pairs:
            np.copyto(bus, memory)

    return copy


def from_bus(buffer: Any, payload: Any) -> Callable[[], None]:
    """Binds a buffer of bus bytes to the payload they are read into.

    Args:
        buffer: a buffer of the bus struct's length.
        payload: the message's payload, which must outlive the copy.

    Returns:
        The copy: each call reads the buffer's bytes, as they stand, into the payload.
    """
    pairs = _pairs(payload, buffer)

    def copy() -> None:
        """Reads the buffer into the payload."""
        for memory, bus in pairs:
            np.copyto(memory, bus)

    return copy


def serialize(message: Any) -> bytes:
    """A Basilisk message's bytes, as F´ serializes the bus struct that mirrors it.

    A message no bus struct mirrors, or whose bus struct has a member outside
    `fsw.codegen.fields.STRUCT_CODES`, raises `KeyError` naming it.

    Args:
        message: the message's payload.

    Returns:
        The bytes.
    """
    buffer = bytearray(_plan(_payload_class(message)).size)
    to_bus(message, buffer)()
    return bytes(buffer)


def deserialize(bus: str, data: bytes) -> Any:
    """A bus struct's bytes, as F´ serializes it, as a fresh payload of the message it mirrors.

    Bytes of another length than the struct's raise `ValueError`; a struct with a member outside
    `fsw.codegen.fields.STRUCT_CODES` raises `KeyError`, naming it.

    Args:
        bus: the bus struct's qualified name, `Bus.<Name>`.
        data: the bytes.

    Returns:
        The payload class the struct mirrors, by `fsw.payloads.payload_type`, each field set from
        its member's elements.
    """
    payload = payload_type(bus)()
    from_bus(data, payload)()
    return payload
