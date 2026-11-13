"""What a hosted algorithm's estimate is recorded as in a run file."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gnc_cdh.basilisk.algorithm_module import AlgorithmModule

UNITS = {"sigma_BN": "MRP", "r_BN_N": "m", "v_BN_N": "m/s"}
"""The units of each standard output, by its name."""


def estimate_fields(fsw: "AlgorithmModule") -> dict[str, tuple[Any, str, str]]:
    """The estimate's run-file datasets, `est/<output name>`, one per output of the host module.

    Args:
        fsw: the host module.

    Returns:
        Each dataset path to the `(message, field, units)` it is recorded from.
    """
    return {f"est/{name}": (message, name, UNITS[name]) for name, message in fsw.outputs.items()}
