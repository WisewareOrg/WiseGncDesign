"""The Basilisk host of the C&DH partition.

`AlgorithmModule` hosts an algorithm against Basilisk's sensor messages, wired by the names it uses,
as an F´ component instance on the ground's link.
"""

from gnc_cdh.basilisk.algorithm_module import AlgorithmModule

__all__ = ["AlgorithmModule"]
