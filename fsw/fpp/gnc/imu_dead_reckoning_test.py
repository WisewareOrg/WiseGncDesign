"""The dead reckoner's GNC sub-topology: nav's rate group and divider, read from its FPP and flown.

Reading the FPP needs the F´ framework clone `just _sync` fetches; flying it needs the deployment
`just fsw` builds, and is skipped without it.
"""

import numpy as np
import pytest

from fsw.codegen.deployment import FPP_FILES
from fsw.codegen.fpp_model import Connection, read
from ground.dictionary import Dictionary
from ground.fprime_station import FprimeStation
from lab import DICTIONARY, extension

NS = 1_000_000_000
"""ns per s."""


def test_the_sub_topology_runs_nav_in_its_rate_group_at_nav_s_divider():
    """Nav is its rate group's one member, run by the driver's first output every tick."""
    model = read(FPP_FILES)

    assert model.topologies["ImuDeadReckoning.Gnc"] == (
        Connection(
            "ImuDeadReckoning.navRateGroup",
            "RateGroupMemberOut",
            0,
            "ImuDeadReckoning.nav",
            "schedIn",
            0,
        ),
    )
    assert (
        Connection(
            "WiseFsw.rateGroupDriver", "CycleOut", 0, "ImuDeadReckoning.navRateGroup", "CycleIn", 0
        )
        in model.topologies["WiseFsw.WiseFsw"]
    )
    assert model.constants["ImuDeadReckoning.navDivider"] == 1


def test_the_fprime_build_runs_nav_once_every_nav_divider_ticks():
    """Nav writes its state once per run, so `10 * navDivider` ticks give exactly 10 writes.

    The driver's tick count carries over from earlier tests in the process, so the count is taken
    over a whole number of dividers, which holds whatever tick the driver starts on.
    """
    pytest.importorskip("lab._wise_fsw", reason="the F´ build is absent; run `just fsw`")
    fsw = extension()
    station = FprimeStation(fsw, Dictionary(DICTIONARY))
    divider = read(FPP_FILES).constants["ImuDeadReckoning.navDivider"]
    ticks = 10 * divider
    fsw.boot(mu=3.986004360e14, dcm_PB=np.eye(3))
    station.telemetry()

    for tick in range(1, ticks + 1):
        fsw.step(t_ns=tick * NS, angVelPlatform=np.zeros(3), accelPlatform=np.zeros(3))

    writes = [name for name, _, _ in station.telemetry() if name == "nav.navState"]
    assert len(writes) == ticks // divider
