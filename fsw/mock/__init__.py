"""Every committed test mock, as one contract, and the plumbing tests render mocks with.

`MockGnc.fpp` is two mock algorithms, a source feeding a sink, flown by `gnc/MockFrame.fpp`.
`HarnessMock.fpp` and its notebook `mock.py` are laid out as an algorithm's are, and
`gnc/MockFlight.fpp` flies it as the nav role. `MOCK` is the contract, which a test flies with
`contract=MOCK`.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from fsw.codegen.deployment import Contract

__all__ = ["ARGS", "MOCK", "edited", "sub_topology"]

_HERE = Path(__file__).resolve().parent

MOCK = Contract((_HERE / "MockGnc.fpp", _HERE / "HarnessMock.fpp"), _HERE / "gnc")
"""The test mocks' contract: `MockGnc.fpp`, `HarnessMock.fpp`, and the configurations in `gnc/`."""

ARGS = {
    "gain": 0.1,
    "enabled": True,
    "mode": "fast",
    "offset": [1.0, 2.0, 3.0],
    "mounting": np.arange(9.0).reshape(3, 3),
    "count": 7,
}
"""The arguments of the ground dictionary test mock's `setMock` command, by name."""


def edited(text: str, *edits: tuple[str, str]) -> str:
    """A test mock's text with edits applied in order, each required to find its text.

    Args:
        text: the mock's text.
        *edits: each `(old, new)`, every `old` replaced with `new`.

    Returns:
        The edited text.
    """
    for old, new in edits:
        assert old in text, old
        text = text.replace(old, new)
    return text


_SUB_TOPOLOGY = """module {name} {{
  constant tickPeriod = 1.0
  constant mockDivider = 1
  instance rateGroupDriver: Svc.RateGroupDriver base id 0x6000
  instance mockRateGroup: Svc.PassiveRateGroup base id 0x6100
{instances}
  topology Gnc {{
    instance rateGroupDriver
    instance mockRateGroup
{uses}
    connections RateGroups {{
      rateGroupDriver.CycleOut[0] -> mockRateGroup.CycleIn
{wires}
    }}
    port tickIn = rateGroupDriver.CycleIn
{ports}  }}
}}
"""
"""A test mock configuration: one rate group running its members in order."""


def sub_topology(name: str, members: Sequence[tuple[str, str]], ports: Sequence[str] = ()) -> str:
    """A test mock configuration's GNC sub-topology: one rate group running its members in order.

    Args:
        name: the configuration's name, its module's.
        members: each member's `(instance, component)`, in the order they run.
        ports: each further topology port's declaration, such as `port imuIn = sink.imuIn`.

    Returns:
        The sub-topology's FPP.
    """
    return _SUB_TOPOLOGY.format(
        name=name,
        instances="".join(
            f"  instance {i}: {c} base id {0x6200 + 0x100 * n:#x}\n"
            for n, (i, c) in enumerate(members)
        ),
        uses="".join(f"    instance {i}\n" for i, _ in members),
        wires="\n".join(
            f"      mockRateGroup.RateGroupMemberOut[{n}] -> {i}.schedIn"
            for n, (i, _) in enumerate(members)
        ),
        ports="".join(f"    {port}\n" for port in ports),
    )
