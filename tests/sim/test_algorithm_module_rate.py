"""`AlgorithmModule` hosted in a WiseDynamics scenario."""

import numpy as np
from Basilisk.architecture import messaging
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from gnc_cdh.basilisk import AlgorithmModule


class RateStub:
    """A stub algorithm that reads `AngVelPlatform` and holds `t`, `r_BN_N` and `v_BN_N`."""

    def __init__(self) -> None:
        """Starts the stub at t = 0 with zero position and velocity."""
        self.t = 0.0
        self.r_BN_N = np.zeros(3)
        self.v_BN_N = np.zeros(3)

    def step(self, t: float, AngVelPlatform: np.ndarray) -> dict:
        """Advances `t` and returns the unchanged outputs.

        Args:
            t: s, the step's time.
            AngVelPlatform: (3,) rad/s, read from the IMU message.

        Returns:
            `r_BN_N` ((3,) m, in N) and `v_BN_N` ((3,) m/s, in N) as named arrays.
        """
        self.t = t
        return {"r_BN_N": self.r_BN_N, "v_BN_N": self.v_BN_N}


def test_the_outputs_are_written_at_whole_seconds_not_at_the_dynamics_step():
    """Run 3.5 s in Leo500, the outputs are last written at 3 s: the module's 1 s `period_s`."""
    scenario = Leo500()
    module = AlgorithmModule(RateStub(), scenario.vehicle.readers())
    nav_trans = messaging.NavTransMsgReader()
    nav_trans.subscribeTo(module.output_messages["nav_trans"])

    scenario.run(module, {}, duration_s=3.5)

    assert nav_trans.timeWritten() == 3_000_000_000
    assert module.algorithm.t == 3.0
