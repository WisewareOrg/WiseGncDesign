"""The Python build's parameters: one component's, read from the case's record.

The record is the JSON the ground writes, `ground.parameters`, keyed by each instance's qualified
name; the F´ build's PrmDb loads the `.dat` F´'s tool makes from the same record.
"""

import json
from pathlib import Path
from typing import Any

from fsw.codegen.deployment import gnc_instance
from fsw.codegen.fpp_types import parameters_from

__all__ = ["read"]


def read(path: Path, tuple_type: type) -> Any:
    """A component's parameters from the case's record.

    The entry is the one under the qualified name of the component's instance in the GNC
    sub-topologies, as the ground writes it. A parameter missing from it, or one the component
    lacks, raises the tuple's `TypeError`.

    Args:
        path: the case's record.
        tuple_type: the component's `<Name>Parameters` tuple.

    Returns:
        The tuple, each array a fresh array of its FPP type.

    Raises:
        KeyError: naming the instance, when the record has no entry for it.
    """
    instance = gnc_instance(tuple_type.component).name
    entries = json.loads(Path(path).read_text())
    if instance not in entries:
        raise KeyError(f"{path} has no parameters for {instance}; it has {sorted(entries)}")
    return parameters_from(tuple_type, entries[instance])
