"""The Python build of the flight software.

`FrameRunner` runs a configuration's partitions, RIO, CDH, GNC and platform, one frame per base
tick, as the build WiseDynamics' `FswHost` hosts, on the ground's radio edge.
"""

from fsw.python.platform import FrameRunner

__all__ = ["FrameRunner"]
