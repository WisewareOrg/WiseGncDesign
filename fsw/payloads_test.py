"""Each bus struct's Basilisk payload class, by the name rule bus_test.py holds.

The rule ranges over every bus struct in `Bus.fpp`.
"""

from pathlib import Path

import pytest
from Basilisk.architecture import messaging

from fsw.codegen.fpp_model import Struct, read
from fsw.payloads import payload_type

BUS = Path(__file__).parent / "fpp" / "interfaces" / "Bus.fpp"
"""The bus structs' FPP file."""


def test_each_bus_struct_s_payload_is_messaging_s_class_of_its_name_ignoring_case():
    """`Bus.<Name>` gives `messaging.<Name>Payload`, matched ignoring case, as bus_test.py does."""
    structs = [n for n, t in read([BUS]).types.items() if isinstance(t, Struct)]
    assert structs
    for name in structs:
        found = payload_type(name)
        assert getattr(messaging, found.__name__) is found, name
        assert found.__name__.lower() == name.removeprefix("Bus.").lower() + "payload", name
    assert payload_type("Bus.ImuSensorMsg") is messaging.IMUSensorMsgPayload


def test_a_bus_struct_no_payload_mirrors_is_refused_naming_it():
    """A name with no `messaging` payload class raises `KeyError`, naming the struct."""
    with pytest.raises(KeyError, match=r"Bus\.NotAMessage"):
        payload_type("Bus.NotAMessage")
