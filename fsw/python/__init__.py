"""The Basilisk host of the flight software.

`AlgorithmModule` hosts an algorithm against Basilisk's sensor messages, wired by the names it uses,
as an F´ component instance on the ground's link.
"""

from fsw.python.host import AlgorithmModule

__all__ = ["AlgorithmModule"]
