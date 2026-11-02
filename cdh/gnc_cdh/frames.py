"""The frame transforms a host applies to an input before it reaches an algorithm, by neutral
name.

A mounting is the DCM [PB] from the body frame B to a sensor's own platform frame P, so that
v_P = [PB] v_B.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import numpy as np

__all__ = ["TRANSFORMS", "platform_to_body"]


def platform_to_body(dcm_PB: np.ndarray, value_P: np.ndarray) -> np.ndarray:
    """Rotates a (3,) vector from a sensor's platform frame P into the body frame B:
    v_B = [PB]^T v_P."""
    return dcm_PB.T @ value_P


TRANSFORMS: Mapping[str, Callable[[np.ndarray, np.ndarray], np.ndarray]] = MappingProxyType(
    {"platform_to_body": platform_to_body}
)
"""Every frame transform a binding may name, as `transform(mounting, value)`."""
