"""The lab: test-rack equipment that hosts each configuration's F´ deployment in the simulation.

`just fsw` builds each configuration's deployment into this package as `_wise_fsw_<configuration>`,
with its dictionary beside it, `dictionary_path(configuration)`. `Adapter` presents one of them to
WiseDynamics' `FswHost` as a flight-software build.
"""

from lab.adapter import Adapter
from lab.power_cycle import dictionary_path

__all__ = ["Adapter", "dictionary_path"]
