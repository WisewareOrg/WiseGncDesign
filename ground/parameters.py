"""A case's parameters, as the ground hands them to the flight software.

The record is JSON, `{"<qualified instance>": {"<parameter>": value}}`, written beside the case's
run file; both builds fly from it. F´'s own `fprime-prm-write` conversion, called in-process,
makes the `.dat` the F´ build's PrmDb loads, so nothing here parses or writes F´'s binary format.
Why is in ADR 0004 rev 2.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
from fprime_gds.common.tools.params import convert_json

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
    """Makes the record's `.dat` beside it with `fprime-prm-write`'s own conversion, in-process.

    The output path is always given, so the tool never derives one from the record's. A record the
    tool refuses, such as one naming a parameter the dictionary lacks, raises the tool's own
    exception.

    Args:
        record: the case's record, `<name>.json`.
        dictionary: the F´ deployment's dictionary.

    Returns:
        The `.dat`, `<name>.dat`.
    """
    output = record.with_suffix(".dat")
    convert_json(record, dictionary, output, "dat")
    return output
