"""Pure dead reckoning: gyro rates integrated to attitude (MRP), accelerometer integrated to
accumulated delta-V in the inertial frame. No correction, no filter."""

from dataclasses import dataclass

import numpy as np

from gnc_algorithms.mrp import B, dcm_NB, shadow


@dataclass
class ImuSample:
    t: float  # s
    omega_B: np.ndarray  # (3,) rad/s, body-frame angular rate
    accel_B: np.ndarray  # (3,) m/s^2, body-frame non-gravitational acceleration


@dataclass
class DeadReckoningState:
    t: float
    sigma_BN: np.ndarray  # (3,) MRP, body wrt inertial
    dv_N: np.ndarray  # (3,) m/s, accumulated delta-V in inertial frame


class ImuDeadReckoner:
    """Propagates attitude (MRP) and accumulated delta-V from raw body-frame IMU samples."""

    def __init__(self, sigma0_BN: np.ndarray, t0: float) -> None:
        self._state = DeadReckoningState(
            t=t0, sigma_BN=np.array(sigma0_BN, dtype=float), dv_N=np.zeros(3)
        )

    @property
    def state(self) -> DeadReckoningState:
        return self._state

    def step(self, sample: ImuSample) -> DeadReckoningState:
        """dt = sample.t - state.t (must be > 0). Propagates sigma with the MRP kinematic
        equation dsigma/dt = 1/4 B(sigma) @ omega, via RK4 over dt with omega held constant;
        switches to the shadow set when |sigma| > 1. Accumulates
        dv_N += dcm_NB(sigma) @ accel_B * dt using sigma at the start of the step. Returns the
        new state."""
        dt = sample.t - self._state.t
        if dt <= 0.0:
            raise ValueError(f"dt must be > 0, got {dt}")

        sigma = self._state.sigma_BN
        omega = np.asarray(sample.omega_B, dtype=float)

        def rate(s: np.ndarray) -> np.ndarray:
            return 0.25 * B(s) @ omega

        k1 = rate(sigma)
        k2 = rate(sigma + 0.5 * dt * k1)
        k3 = rate(sigma + 0.5 * dt * k2)
        k4 = rate(sigma + dt * k3)
        sigma_new = sigma + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        if np.linalg.norm(sigma_new) > 1.0:
            sigma_new = shadow(sigma_new)

        accel = np.asarray(sample.accel_B, dtype=float)
        dv_new = self._state.dv_N + dcm_NB(sigma) @ accel * dt

        self._state = DeadReckoningState(t=sample.t, sigma_BN=sigma_new, dv_N=dv_new)
        return self._state
