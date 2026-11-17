"""The Python build's parameters: one component's, read from the case's record.

The record is the JSON the ground writes, `ground.parameters`, keyed by each instance's qualified
name; the F´ build's PrmDb loads the `.dat` F´'s tool makes from the same record.
"""

import json
from pathlib import Path
from typing import Any

from fsw.codegen.fpp_types import named, parameters_from

__all__ = ["read", "tuple_of"]


def tuple_of(component: str) -> type:
    """A component's parameters tuple, `<Name>Parameters`.

    Args:
        component: the component's qualified FPP name, `<module>.<component>`.

    Returns:
        The tuple.
    """
    return named(f"{component}Parameters")


def read(path: Path, tuple_type: type, instance: str) -> Any:
    """An instance's parameters from the case's record.

    The entry is the one under the instance's qualified name, as the ground writes it. A parameter
    missing from it, or one the component lacks, raises the tuple's `TypeError`.

    Args:
        path: the case's record.
        tuple_type: the instance's component's `<Name>Parameters` tuple.
        instance: the instance's qualified name, `<configuration>.<instance>`.

    Returns:
        The tuple, each array a fresh array of its FPP type.

    Raises:
        KeyError: naming the instance, when the record has no entry for it.
    """
    entries = json.loads(Path(path).read_text())
    if instance not in entries:
        raise KeyError(f"{path} has no parameters for {instance}; it has {sorted(entries)}")
    return parameters_from(tuple_type, entries[instance])
