"""A case's parameters, as the ground hands them to the flight software.

The record is JSON, `{"<qualified instance>": {"<parameter>": value}}`, written beside the case's
run file; both builds fly from it. F´'s own `fprime-prm-write` conversion, called in-process,
makes the `.dat` the F´ build's PrmDb loads, so nothing here parses or writes F´'s binary format.
Why is in ADR 0004 rev 2.
"""

import contextlib
import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from fprime_gds.common.tools.params import convert_json

from fsw.codegen.deployment import gnc_instance

__all__ = ["dat", "write"]


def write(parameters: Sequence[Any], path: Path) -> Path:
    """Writes components' parameters as the case's record.

    Each tuple is keyed by the qualified name of the one instance of its component in the GNC
    sub-topologies, and every field of it is written, an array as nested lists.

    Args:
        parameters: each component's `<Name>Parameters` tuple.
        path: the record's path.

    Returns:
        `path`.

    Raises:
        ValueError: two tuples are of one component's instance, naming it.
    """
    record = {}
    for tuple_ in parameters:
        instance = gnc_instance(type(tuple_).component).name
        if instance in record:
            raise ValueError(f"two parameters tuples are of {instance}")
        record[instance] = {
            name: value.tolist() if isinstance(value, np.ndarray) else value
            for name, value in tuple_._asdict().items()
        }
    path.write_text(json.dumps(record))
    return path


def dat(record: Path, dictionary: Path) -> Path:
    """Makes the record's `.dat` beside it with `fprime-prm-write`'s own conversion, in-process.

    What the tool prints is discarded. A record the tool refuses, such as one naming a parameter
    the dictionary lacks, raises the tool's own exception.

    Args:
        record: the case's record, `<name>.json`.
        dictionary: the F´ deployment's dictionary.

    Returns:
        The `.dat`, `<name>.dat`.
    """
    output = record.with_suffix(".dat")
    with contextlib.redirect_stdout(io.StringIO()):
        convert_json(record, dictionary, output, "dat")
    return output
