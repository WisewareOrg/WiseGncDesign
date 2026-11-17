"""Each bus struct's Basilisk payload class: the one rule both builds' RIO and the lab share.

A bus struct `Bus.<Name>` mirrors `Basilisk.architecture.messaging.<Name>Payload`, matched ignoring
case, as `fsw/fpp/interfaces/bus_test.py` holds them. It lives outside `fsw.codegen`, which reads
FPP alone and never imports Basilisk.
"""

import functools

from Basilisk.architecture import messaging

__all__ = ["payload_type"]


@functools.cache
def _payloads() -> dict[str, type]:
    """Each of `messaging`'s payload classes, by its name in lower case, read once.

    Returns:
        The classes.
    """
    return {n.lower(): getattr(messaging, n) for n in dir(messaging) if n.endswith("Payload")}


def payload_type(bus: str) -> type:
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
