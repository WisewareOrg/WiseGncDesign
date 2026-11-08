"""The Basilisk host of the C&DH partition.

`AlgorithmModule` hosts an algorithm against Basilisk messages, wired by the names it uses.
"""

from gnc_cdh.basilisk.algorithm_module import STANDARD_MESSAGES, AlgorithmModule

__all__ = ["STANDARD_MESSAGES", "AlgorithmModule"]
