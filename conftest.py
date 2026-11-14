"""Fixtures every package's tests share: an F´ copy, its station, a drain, a case's parameters.

A fixture needing the F´ build, or the dictionary it generates, skips its test without it. Every
pytest run loads this file, the judge's included, so the FPP model, Basilisk and F´ are imported
only by the fixtures that need them.
"""

from __future__ import annotations

import functools
import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

if TYPE_CHECKING:
    from ground.fprime_station import FprimeStation


@pytest.fixture
def fsw() -> ModuleType:
    """A fresh copy of the deployment, not yet booted; skips the test without the F´ build.

    Returns:
        The copy.
    """
    if importlib.util.find_spec("lab._wise_fsw") is None:
        pytest.skip("the F´ build is absent; run `just fsw`")
    from lab.power_cycle import power_cycle

    return power_cycle()


@pytest.fixture
def station(fsw: ModuleType) -> FprimeStation:
    """The ground station on the test's copy, on the dictionary the build generated.

    Args:
        fsw: the test's copy.

    Returns:
        The station.
    """
    from ground.dictionary import Dictionary
    from ground.fprime_station import FprimeStation
    from lab import DICTIONARY

    return FprimeStation(fsw, Dictionary(DICTIONARY))


@pytest.fixture
def decoded() -> Callable[[Any], list[tuple[str, int, Any]]]:
    """A drain of an edge's telemetry, each write decoded to its value by the edge.

    Returns:
        A function taking an edge, such as an `FprimeStation` or a `lab.FprimeModule`, and giving
        each write since the edge's last drain as `(<instance>.<channel>, time tag in ns, value)`,
        oldest first.
    """

    def drain(edge: Any) -> list[tuple[str, int, Any]]:
        """Drains the edge's telemetry writes, each as its value.

        Args:
            edge: the edge.

        Returns:
            Each write's channel name, time tag in ns and value, oldest first.
        """
        return [(name, t_ns, edge.values(name, [raw])[0]) for name, t_ns, raw in edge.telemetry()]

    return drain


@pytest.fixture(scope="session")
def case_parameters() -> tuple[Any, ...]:
    """Each algorithm's GNC instance's parameters, every value zero, of its FPP shape.

    Returns:
        Each instance's `<Name>Parameters` tuple.
    """
    from fsw.codegen import fpp_types
    from fsw.codegen.deployment import algorithm_files, contract_files, gnc_instances
    from fsw.codegen.fpp_model import Array, read

    model = read(contract_files())
    algorithms = set(algorithm_files())
    tuples = []
    for instance in gnc_instances():
        component = model.components.get(instance.component)
        if component is None or component.file not in algorithms:
            continue
        values = {}
        for parameter in component.parameters:
            shape, type_name = (), parameter.type
            while isinstance(array := model.types.get(type_name), Array):
                shape, type_name = (*shape, array.size), array.element
            values[parameter.name] = np.zeros(shape).tolist()
        tuple_type = functools.reduce(getattr, f"{component.name}Parameters".split("."), fpp_types)
        tuples.append(fpp_types.parameters_from(tuple_type, values))
    return tuple(tuples)


@pytest.fixture
def prm_record(case_parameters: tuple[Any, ...], tmp_path: Path) -> Path:
    """A case's parameter record, written as the ground writes it, in a case directory of its own.

    Args:
        case_parameters: the case's parameters tuples.
        tmp_path: the test's directory, which holds the case directory `case`.

    Returns:
        The record, `case/run_0000.prm.json`.
    """
    from ground import parameters

    case = tmp_path / "case"
    case.mkdir()
    return parameters.write(case_parameters, case / "run_0000.prm.json")


@pytest.fixture
def prm(prm_record: Path) -> str:
    """The case's `.dat`, made beside its record as the F´ host makes it.

    Args:
        prm_record: the case's record.

    Returns:
        The `.dat`'s path, as `boot` takes it.
    """
    from ground import parameters

    return str(parameters.dat(prm_record, _dictionary()))


@pytest.fixture(scope="session")
def parameter_ids() -> list[int]:
    """Every parameter's ID in the deployment's dictionary, which `boot` holds valid.

    Returns:
        The IDs, sorted.
    """
    from ground.dictionary import Dictionary

    return sorted(Dictionary(_dictionary()).parameters_by_id)


def _dictionary() -> Path:
    """The deployment's dictionary, skipping the test asking when `just fsw` has not built it.

    Returns:
        Its path.
    """
    from lab import DICTIONARY

    if not DICTIONARY.exists():
        pytest.skip("the F´ build is absent; run `just fsw`")
    return DICTIONARY
