"""Each bus struct's Basilisk payload class, by the name rule `fsw.payloads` holds.

`fsw/fpp/interfaces/bus_test.py` ranges over every bus struct in `Bus.fpp` through `payload_type`.
"""

import subprocess

import pytest
from Basilisk.architecture import messaging

from fsw.codegen.deployment import REPOSITORY
from fsw.payloads import payload_type


def test_a_bus_struct_s_payload_is_messaging_s_class_of_its_name_ignoring_case():
    """`Bus.ImuSensorMsg` gives `messaging.IMUSensorMsgPayload`, whose name is cased otherwise."""
    assert payload_type("Bus.ImuSensorMsg") is messaging.IMUSensorMsgPayload


def test_a_bus_struct_no_payload_mirrors_is_refused_naming_it():
    """A name with no `messaging` payload class raises `KeyError`, naming the struct."""
    with pytest.raises(KeyError, match=r"Bus\.NotAMessage"):
        payload_type("Bus.NotAMessage")


def test_the_name_rule_is_written_in_one_place():
    """No Python file but `fsw/payloads.py` appends `payload` to a bus struct's lower-cased name."""
    found = subprocess.run(
        ["git", "grep", "-lE", r'lower\(\) \+ "payload"', "--", "*.py"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
    ).stdout

    assert found.split() == ["fsw/payloads.py"]
