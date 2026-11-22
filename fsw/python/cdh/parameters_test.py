"""The Python build's CDH reads each algorithm instance's parameters from the case's record.

The parameters are every algorithm component's, generated from the contract.
"""

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fsw.python.cdh import parameters


def _instance(component: str) -> str:
    """A qualified instance name for a component's tuple, of a mock configuration.

    Args:
        component: the component's qualified name.

    Returns:
        `MockConfiguration.<Name>`.
    """
    return f"MockConfiguration.{component.rsplit('.', 1)[-1]}"


def _record(directory: Path, entries: dict) -> Path:
    """A case's record, written by hand.

    Args:
        directory: where to write it.
        entries: the JSON object.

    Returns:
        Its path.
    """
    path = directory / "run_0000.prm.json"
    path.write_text(json.dumps(entries))
    return path


def _values(tuple_: Any) -> dict[str, Any]:
    """A parameters tuple's fields as plain values, an array as nested lists.

    Args:
        tuple_: the tuple.

    Returns:
        Each field's value by name.
    """
    return {name: np.asarray(value).tolist() for name, value in tuple_._asdict().items()}


def test_each_instance_s_parameters_come_back_as_its_tuple(tmp_path: Path, algorithm_parameters: dict[str, Any]):
    """Keyed by the qualified instance, as the ground writes it, an array as a fresh array.

    Args:
        tmp_path: where the record is written.
        algorithm_parameters: each algorithm component's tuple.
    """
    assert algorithm_parameters
    entries = {_instance(c): _values(t) for c, t in algorithm_parameters.items()}
    record = _record(tmp_path, entries)

    for component, expected in algorithm_parameters.items():
        read = parameters.read(record, type(expected), _instance(component))

        assert type(read) is type(expected)
        for name, value in expected._asdict().items():
            if isinstance(value, np.ndarray):
                assert isinstance(getattr(read, name), np.ndarray), f"{component}.{name}"
                assert getattr(read, name).dtype == value.dtype, f"{component}.{name}"
            np.testing.assert_array_equal(getattr(read, name), value, err_msg=component)


@pytest.mark.parametrize("change", ["drop", "add"])
def test_a_parameter_the_record_lacks_or_the_component_lacks_raises_naming_it(
    tmp_path: Path, algorithm_parameters: dict[str, Any], change: str
):
    """A record without one of an instance's parameters, or naming one the tuple lacks, fails.

    The first fails as the F´ build's boot does, the second as F´'s tool does.

    Args:
        tmp_path: where the record is written.
        algorithm_parameters: each algorithm component's tuple.
        change: `drop` removes a parameter from the record, `add` names one the component lacks.
    """
    for component, tuple_ in algorithm_parameters.items():
        values = _values(tuple_)
        if change == "drop":
            if not values:
                continue
            name = sorted(values)[0]
            del values[name]
        else:
            name = "notAParameter"
            values[name] = 1.0
        record = _record(tmp_path, {_instance(component): values})

        with pytest.raises(TypeError, match=re.escape(name)):
            parameters.read(record, type(tuple_), _instance(component))


def test_a_record_without_the_instance_raises_naming_it(tmp_path: Path, algorithm_parameters: dict[str, Any]):
    """An entry under another qualified name is not the instance's.

    Args:
        tmp_path: where the record is written.
        algorithm_parameters: each algorithm component's tuple.
    """
    for component, tuple_ in algorithm_parameters.items():
        instance = _instance(component)
        record = _record(tmp_path, {f"Other.{instance}": _values(tuple_)})

        with pytest.raises(KeyError, match=re.escape(f"no parameters for {instance}")):
            parameters.read(record, type(tuple_), _instance(component))
