"""The harness's test mock: one algorithm of its own, and one configuration flying it.

`HarnessMock.fpp` and its notebook `mock.py` are laid out as an algorithm's are, and `gnc/` holds
the configuration `MockFlight`. `MOCK` is the contract, which a test's `Mission` flies with
`contract=MOCK`.
"""

from pathlib import Path

from fsw.codegen.deployment import Contract

__all__ = ["MOCK"]

_HERE = Path(__file__).resolve().parent

MOCK = Contract((_HERE / "HarnessMock.fpp",), _HERE / "gnc")
"""The test mock's contract: `HarnessMock.fpp`, and the configuration in `gnc/`."""
