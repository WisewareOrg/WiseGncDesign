"""Quaternion math the numba-compiled algorithms call, where SciPy cannot be called."""

from algorithms.utils.quaternion.quaternion import dcm_NB, multiply

__all__ = ["dcm_NB", "multiply"]
