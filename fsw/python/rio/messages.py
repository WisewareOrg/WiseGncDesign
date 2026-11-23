"""The Python build's RIO: each sensor role's Basilisk message read as its bus struct, and back.

Each role's reading is planned once, from the payload class its bus struct mirrors by
`fsw.payloads.payload_type`, its fields matched by `fsw.codegen.fpp_types.fields`. RIO-in reads a payload into
a fresh, read-only copy: the host's payload is a live view of its message, which the next dynamics
step overwrites, and CDH-in passes the copy's arrays to GNC uncopied. SWIG can return the payload as
another module's class of the same name, such as a simulation module's once that module is imported;
that class is a proxy of the same C struct, so it reads alike. RIO-out writes each actuator role's
bus struct into a fresh payload of that class, each field from the bus member of its name, ignoring
case.
"""

import ctypes
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from fsw.codegen.fpp_types import fields
from fsw.payloads import payload_type
from fsw.python.cdh.inputs import Pair

__all__ = ["check", "reader", "writer"]


def check(pairs: Sequence[Pair], messages_by_role: Mapping[str, Any]) -> None:
    """Checks each paired role has a message, of the payload class its bus struct mirrors.

    A role no pair names is not read, so not checked.

    Args:
        pairs: the sensor roles' pairs.
        messages_by_role: each role's Basilisk message payload, as the host gives it.

    Raises:
        KeyError: a paired role has no message, naming it.
        TypeError: a role's payload is of another class than its bus struct mirrors, by name,
            naming both.
    """
    for pair in pairs:
        if pair.role not in messages_by_role:
            raise KeyError(
                f"the configuration takes the role {pair.role}, which the vehicle's messages"
                f" {sorted(messages_by_role)} lack"
            )
        given = type(messages_by_role[pair.role]).__name__
        wanted = payload_type(pair.bus.__qualname__).__name__
        if given != wanted:
            raise TypeError(f"the role {pair.role}'s message is a {given}, but its bus struct mirrors {wanted}")


def reader(bus: type[Any], payload: type[Any] | None = None) -> Callable[[Any], Any]:
    """RIO-in for one bus struct: a payload, read as a bus driver reads a buffer.

    The payload's C struct is copied once and viewed as its class's `__dtype__`: each array field
    of the bus struct is a read-only array over that copy, and each scalar a number. Its fields are
    matched by `fsw.codegen.fpp_types.fields`, once.

    Args:
        bus: the bus struct's tuple.
        payload: the payload class read, by default the one `bus` mirrors by
            `fsw.payloads.payload_type`.

    Returns:
        A function of a payload, a SWIG proxy whose `this` is its C struct's address, returning the
        bus struct's tuple.
    """
    source: type[Any] = payload_type(bus.__qualname__) if payload is None else payload
    layout = source.__dtype__
    taken = [(name, bool(shape)) for _, name, (shape, _) in fields(source, bus)]

    def read(value: Any) -> Any:
        """The bus struct of a payload.

        Args:
            value: the payload.

        Returns:
            The bus struct's tuple.
        """
        record = np.frombuffer(ctypes.string_at(int(value.this), layout.itemsize), layout)[0]
        return bus._make([record[name] if array else record[name].item() for name, array in taken])

    return read


def writer(bus: type[Any], payload: type[Any] | None = None) -> Callable[[Any], Any]:
    """RIO-out for one bus struct: written into a fresh payload's memory.

    Each field is copied into the payload's C struct at its class's `__dtype__` offset; a value of
    another shape than its field's is refused rather than broadcast into it.

    Args:
        bus: the bus struct's tuple.
        payload: the payload class written, by default the one `bus` mirrors by
            `fsw.payloads.payload_type`.

    Returns:
        A function of the bus struct's tuple, returning a fresh payload.
    """
    target: type[Any] = payload_type(bus.__qualname__) if payload is None else payload
    layout = target.__dtype__
    taken = [(member.name, name, shape) for member, name, (shape, _) in fields(target, bus)]

    def write(value: Any) -> Any:
        """A fresh payload holding a bus struct.

        Args:
            value: the bus struct's tuple.

        Returns:
            The payload.

        Raises:
            ValueError: a field's value is of another shape than the field, naming it.
        """
        written = target()
        record = np.frombuffer((ctypes.c_char * layout.itemsize).from_address(int(written.this)), layout)
        for (member_name, name, shape), field in zip(taken, value, strict=True):
            if np.shape(field) != shape:
                raise ValueError(f"{bus.__name__}.{member_name} is {shape}, but its value is {np.shape(field)}")
            record[name][0] = field
        return written

    return write
