"""A configuration's members: each rate group's, in the order its sub-topology's FPP gives them.

The sub-topology is a test mock written in `tmp_path`, wired out of declaration order so that only
the connections' port numbers can give the order found.
"""

from pathlib import Path

import pytest

from fsw.codegen.deployment import framework_files
from fsw.codegen.fpp_model import Instance, Model, read
from fsw.codegen.members import members

MOCK = """
module MembersMock {{

  passive component Member {{
    sync input port schedIn: Svc.Sched
  }}

  instance driver: Svc.RateGroupDriver base id 0x100
{extra}
  instance slow: Svc.PassiveRateGroup base id 0x200

  instance fast: Svc.PassiveRateGroup base id 0x300

  instance a: Member base id 0x400

  instance b: Member base id 0x500

  instance c: Member base id 0x600

  topology Gnc {{

    instance driver
{extra_use}
    instance slow
    instance fast
    instance a
    instance b
    instance c

    connections RateGroups {{
      driver.CycleOut[1] -> slow.CycleIn
      driver.CycleOut[0] -> fast.CycleIn
{extra_wire}
      fast.RateGroupMemberOut[1] -> a.schedIn
      fast.RateGroupMemberOut[0] -> c.schedIn
      slow.RateGroupMemberOut[0] -> b.schedIn
    }}

  }}

}}
"""


def _model(tmp_path: Path, second_driver: bool = False) -> Model:
    """The test mock's model, optionally with a second rate group driver.

    Args:
        tmp_path: where the mock's FPP is written.
        second_driver: whether the sub-topology has a second driver.

    Returns:
        The model, the F´ framework's files and the mock's.
    """
    fpp = tmp_path / "MembersMock.fpp"
    fpp.write_text(
        MOCK.format(
            extra="\n  instance other: Svc.RateGroupDriver base id 0x700\n"
            if second_driver
            else "",
            extra_use="    instance other" if second_driver else "",
            extra_wire="      other.CycleOut[0] -> slow.CycleIn" if second_driver else "",
        )
    )
    return read((*framework_files(), fpp))


def test_each_rate_group_s_members_are_in_their_port_order_under_the_driver_s_order(
    tmp_path: Path,
):
    """`fast` is on `CycleOut[0]`, so it comes first; its members run `c`, then `a`.

    Args:
        tmp_path: where the mock's FPP is written.
    """
    member = "MembersMock.Member"

    assert list(members(_model(tmp_path), "MembersMock").items()) == [
        (
            "MembersMock.fast",
            (Instance("MembersMock.c", member, 0x600), Instance("MembersMock.a", member, 0x400)),
        ),
        ("MembersMock.slow", (Instance("MembersMock.b", member, 0x500),)),
    ]


def test_a_sub_topology_with_two_drivers_is_refused_naming_them(tmp_path: Path):
    """Two drivers leave no one order of rate groups; both are named.

    Args:
        tmp_path: where the mock's FPP is written.
    """
    with pytest.raises(
        ValueError,
        match=r"MembersMock\.Gnc has 2 rate group drivers: "
        r"\['MembersMock\.driver', 'MembersMock\.other'\]",
    ):
        members(_model(tmp_path, second_driver=True), "MembersMock")
