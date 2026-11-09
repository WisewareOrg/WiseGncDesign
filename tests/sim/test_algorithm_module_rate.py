"""`AlgorithmModule` hosted in a WiseDynamics scenario."""

from Basilisk.architecture import messaging
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from gnc_algorithms.imu_dead_reckoning import dead_reckoner


def test_a_hosted_algorithm_writes_at_its_module_period():
    """Run 3.5 s in Leo500, the estimate is last written at 3 s, the module's 1 s `period_s`."""
    scenario = Leo500()
    fsw = dead_reckoner(scenario)
    estimate = messaging.NavAttMsgReader()
    estimate.subscribeTo(fsw.output_messages["nav_att"])

    scenario.run(fsw, {}, duration_s=3.5)

    assert estimate.timeWritten() == 3_000_000_000
    assert fsw.algorithm.t == 3.0
