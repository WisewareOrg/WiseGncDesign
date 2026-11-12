"""The F´ host of the C&DH partition: the WiseFsw deployment, run inside the simulation.

`FprimeModule` runs the deployment `just fsw` builds into this package, `_wise_fsw`.
"""

from gnc_cdh.fprime.module import DICTIONARY, FprimeModule, decoders, telemetry_by_name

__all__ = ["DICTIONARY", "FprimeModule", "decoders", "telemetry_by_name"]
