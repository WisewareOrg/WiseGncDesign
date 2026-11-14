"""A case's parameters, as the ground hands them to the flight software.

The record is JSON, `{"<qualified instance>": {"<parameter>": value}}`, written beside the case's
run file; both builds fly from it. F´'s own `fprime-prm-write` makes the `.dat` the F´ build's
PrmDb loads, so nothing here parses or writes F´'s binary format. Why is in ADR 0004 rev 2.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

from fsw.codegen.deployment import gnc_instance

__all__ = ["dat", "write"]


def write(parameters: Any, path: Path) -> Path:
    """Writes one component's parameters as the case's record.

    The key is the qualified name of the one instance of the tuple's component in the GNC
    sub-topologies, and every field of the tuple is written, an array as nested lists.

    Args:
        parameters: a component's `<Name>Parameters` tuple.
        path: the record's path.

    Returns:
        `path`.
    """
    instance = gnc_instance(type(parameters).component)
    values = {
        name: value.tolist() if isinstance(value, np.ndarray) else value
        for name, value in parameters._asdict().items()
    }
    path.write_text(json.dumps({instance.name: values}))
    return path


def dat(record: Path, dictionary: Path) -> Path:
    """Makes the record's `.dat` beside it with F´'s `fprime-prm-write`.

    Args:
        record: the case's record, `<name>.json`.
        dictionary: the F´ deployment's dictionary.

    Returns:
        The `.dat`, `<name>.dat`.

    Raises:
        RuntimeError: carrying the tool's output, when it refuses the record.
    """
    output = record.with_suffix(".dat")
    tool = Path(sys.executable).parent / "fprime-prm-write"
    command = [tool, "dat", record, "-d", dictionary, "-o", output]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"fprime-prm-write refused {record}:\n{result.stdout}{result.stderr}")
    return output
