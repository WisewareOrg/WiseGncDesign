"""The harness's test mock: algorithms of its own and the GNC sub-topologies that fly them.

Each folder but `gnc/` is laid out as an algorithm's is, its components' `.fpp` beside its
notebook, `<folder>/<folder>.py`; `gnc/` holds a sub-topology per configuration. `MOCK` is its
contract, which a test's `Mission` flies with `contract=MOCK`.
"""

from pathlib import Path

from fsw.codegen.deployment import Contract

__all__ = ["MOCK"]

_HERE = Path(__file__).resolve().parent

MOCK = Contract(
    tuple(sorted(p for p in _HERE.glob("*/*.fpp") if p.parent.name != "gnc")), _HERE / "gnc"
)
"""The test mock's contract: every mock algorithm's `.fpp`, and the sub-topologies in `gnc/`."""
