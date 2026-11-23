"""The Python build's RIO: each sensor role's Basilisk message read as its bus struct, and back.

Each bus struct's reading is planned once, from the payload class it mirrors by
`fsw.payloads.payload_type`, its fields matched by `fsw.codegen.fpp_types.fields`. RIO-in binds a
payload to a buffer of its own once; each read copies the payload's C struct into it and gives the
same bus struct, its arrays read-only views of the buffer, as a sampling port does: a reading is
valid for its tick, so GNC copies what it keeps. The host's payload is a live view of its message,
which the next dynamics step overwrites, and CDH-in passes the arrays to GNC uncopied. SWIG can
return the payload as another module's class of the same name, such as a simulation module's once
that module is imported; that class is a proxy of the same C struct, so it reads alike. RIO-out
writes each actuator role's bus struct into the one payload of that class its writer made, each
field from the bus member of its name, ignoring case.
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


def reader(bus: type[Any]) -> Callable[[Any], Callable[[], Any]]:
    """RIO-in for one bus struct: a payload bound to a buffer, read as a bus driver reads one.

    Its fields are matched by `fsw.codegen.fpp_types.fields`, once. A struct of arrays alone gives
    the same tuple at every read; one with a scalar member gives a fresh tuple holding the same
    arrays, since a number cannot be refreshed in place.

    Args:
        bus: the bus struct's tuple, which reads the payload class it mirrors by
            `fsw.payloads.payload_type`.

    Returns:
        A function binding a payload, a SWIG proxy whose `this` is its C struct's address, which
        must outlive the read, and returning its read: each call copies the payload's C struct
        into the buffer and returns the bus struct's tuple.
    """
    source: type[Any] = payload_type(bus.__qualname__)
    layout = source.__dtype__
    taken = [(name, bool(shape)) for _, name, (shape, _) in fields(source, bus)]

    def bind(value: Any) -> Callable[[], Any]:
        """Binds a payload to a buffer of its own.

        Args:
            value: the payload.

        Returns:
            Its read.
        """
        memory = np.frombuffer((ctypes.c_char * layout.itemsize).from_address(int(value.this)), np.uint8)
        buffer = np.zeros(layout.itemsize, np.uint8)
        record = buffer.view(layout)
        views = {}
        for name, array in taken:
            if array:
                view = record[name][0]
                view.flags.writeable = False
                views[name] = view

        if all(array for _, array in taken):
            struct = bus._make([views[name] for name, _ in taken])

            def read() -> Any:
                """Copies the payload into the buffer.

                Returns:
                    The bus struct, the same at every read.
                """
                np.copyto(buffer, memory)
                return struct

            return read

        def read_with_scalars() -> Any:
            """Copies the payload into the buffer.

            Returns:
                A fresh bus struct holding the buffer's arrays and the scalars' values.
            """
            np.copyto(buffer, memory)
            return bus._make([views[name] if array else record[name][0].item() for name, array in taken])

        return read_with_scalars

    return bind


def writer(bus: type[Any]) -> Callable[[Any], Any]:
    """RIO-out for one bus struct: written into one payload's memory, made with the writer.

    Each field is copied into the payload's C struct at its class's `__dtype__` offset; a value of
    another shape than its field's is refused rather than broadcast into it.

    Args:
        bus: the bus struct's tuple, which writes the payload class it mirrors by
            `fsw.payloads.payload_type`.

    Returns:
        A function of the bus struct's tuple, returning the payload, the same at every write.
    """
    target: type[Any] = payload_type(bus.__qualname__)
    layout = target.__dtype__
    written = target()
    record = np.frombuffer((ctypes.c_char * layout.itemsize).from_address(int(written.this)), layout)
    taken = tuple(
        (index, member.name, record[name], shape, len(shape), int(np.prod(shape, dtype=int)))
        for index, (member, name, (shape, _)) in enumerate(fields(target, bus))
    )

    def write(value: Any) -> Any:
        """The payload, holding a bus struct.

        Args:
            value: the bus struct's tuple.

        Returns:
            The payload.

        Raises:
            TypeError: `value` is not of `bus`, naming both.
            ValueError: a field's value is of another shape than the field, naming it.
        """
        if type(value) is not bus:
            raise TypeError(f"the value is a {type(value).__name__}, not the bus struct's tuple {bus.__qualname__}")
        for index, member_name, view, shape, ndim, size in taken:
            field = value[index]
            if isinstance(field, np.ndarray):
                fits = field.ndim == ndim and field.size == size
            else:
                fits = np.shape(field) == shape
            if not fits:
                raise ValueError(f"{bus.__name__}.{member_name} is {shape}, but its value is {np.shape(field)}")
            np.copyto(view, field, casting="unsafe")
        return written

    return write
