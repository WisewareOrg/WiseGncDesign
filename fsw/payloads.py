"""Each bus struct's Basilisk payload class: the one rule both builds' RIO and the lab share.

A bus struct `Bus.<Name>` mirrors `Basilisk.architecture.messaging.<Name>Payload`, matched ignoring
case, as `fsw/fpp/interfaces/bus_test.py` holds them. It lives outside `fsw.codegen`, which reads
FPP alone and never imports Basilisk.
"""

import ctypes
import functools
from collections.abc import Mapping
from typing import Any, ClassVar, Protocol, cast

import numpy as np
from Basilisk.architecture import messaging

__all__ = ["Payload", "PayloadLayout", "memory", "payload_type"]


class PayloadLayout(Protocol):
    """A Basilisk payload's record layout, its class's `__dtype__`: a numpy structured dtype.

    Attributes:
        names: the payload's fields, in Basilisk's order.
        fields: each field's numpy type and byte offset, by its name.
        itemsize: the payload's C struct's size in bytes.
    """

    names: tuple[str, ...]
    fields: Mapping[str, tuple[np.dtype, int] | tuple[np.dtype, int, Any]]
    itemsize: int


class Payload(Protocol):
    """Any of Basilisk's payload classes, found by its name, as this repository reads it.

    Its `__dtype__` is the payload's record layout.
    """

    __dtype__: ClassVar[PayloadLayout]


@functools.cache
def _payloads() -> dict[str, type[Payload]]:
    """Each of `messaging`'s payload classes, by its name in lower case, read once.

    Returns:
        The classes.
    """
    return {n.lower(): getattr(messaging, n) for n in dir(messaging) if n.endswith("Payload")}


def payload_type(bus: str) -> type[Payload]:
    """The Basilisk payload class a bus struct mirrors.

    Args:
        bus: the bus struct's qualified FPP name, `Bus.<Name>`.

    Returns:
        `messaging.<Name>Payload`, its name matched ignoring case.

    Raises:
        KeyError: no payload class mirrors the struct, naming it.
    """
    key = bus.removeprefix("Bus.").lower() + "payload"
    if key not in _payloads():
        raise KeyError(f"no Basilisk payload class in messaging mirrors {bus}")
    return _payloads()[key]


def memory(payload: Any, size: int) -> np.ndarray:
    """A payload's C struct as bytes, a writable view that keeps the payload alive.

    Args:
        payload: a SWIG proxy whose `this` is its C struct's address.
        size: the struct's size in bytes, its class's `__dtype__.itemsize`.

    Returns:
        The bytes, `uint8`, a view of the ctypes array, which holds the payload as its `owner`, so
        the struct outlives every view.
    """
    struct = (ctypes.c_char * size).from_address(int(payload.this))
    cast(Any, struct).owner = payload
    return np.frombuffer(struct, np.uint8)
