"""The F´ host of the flight software: each configuration's deployment, run inside the simulation.

`just fsw` builds each configuration's deployment into this package as `_wise_fsw_<configuration>`,
with its dictionary beside it, `dictionary_path(configuration)`. `FprimeModule` runs one of them.
"""

from lab.module import FprimeModule
from lab.power_cycle import dictionary_path

__all__ = ["FprimeModule", "dictionary_path"]
