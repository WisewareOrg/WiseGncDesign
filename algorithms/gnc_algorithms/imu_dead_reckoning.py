"""Strapdown inertial dead reckoning: gyro rates integrated to attitude (MRP); the body-frame
accelerometer, rotated by that attitude, plus a point-mass gravity model at the estimated
position, integrated to velocity and position. No correction, no filter. The attitude error
feeds the navigation error through the frame rotation."""

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
    r_N: np.ndarray  # (3,) m, inertial position
    v_N: np.ndarray  # (3,) m/s, inertial velocity


def _gravity(r: np.ndarray, mu: float) -> np.ndarray:
    if mu == 0.0:
        return np.zeros(3)
    r_norm = float(np.linalg.norm(r))
    return mu * r / r_norm**3


class ImuDeadReckoner:
    """Propagates attitude (MRP), position and velocity from raw body-frame IMU samples."""

    def __init__(
        self, sigma0_BN: np.ndarray, r0_N: np.ndarray, v0_N: np.ndarray, t0: float, mu: float
    ) -> None:
        self._mu = mu
        self._state = DeadReckoningState(
            t=t0,
            sigma_BN=np.array(sigma0_BN, dtype=float),
            r_N=np.array(r0_N, dtype=float),
            v_N=np.array(v0_N, dtype=float),
        )

    @property
    def state(self) -> DeadReckoningState:
        return self._state

    def step(self, sample: ImuSample) -> DeadReckoningState:
        """dt = sample.t - state.t (must be > 0). One RK4 step over dt of the coupled state
        (sigma, r, v) with omega and accel_B held constant: dsigma/dt = 1/4 B(sigma) @ omega;
        dr/dt = v; dv/dt = dcm_NB(sigma) @ accel_B - mu * r / |r|^3. Switches sigma to the
        shadow set when |sigma| > 1 after the step. Returns the new state."""
        dt = sample.t - self._state.t
        if not dt > 0.0:
            raise ValueError(f"dt must be > 0, got {dt}")

        omega = np.asarray(sample.omega_B, dtype=float)
        accel = np.asarray(sample.accel_B, dtype=float)
        mu = self._mu

        def derivs(
            sigma: np.ndarray, r: np.ndarray, v: np.ndarray
        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            sigma_dot = 0.25 * B(sigma) @ omega
            r_dot = v
            v_dot = dcm_NB(sigma) @ accel - _gravity(r, mu)
            return sigma_dot, r_dot, v_dot

        sigma, r, v = self._state.sigma_BN, self._state.r_N, self._state.v_N

        k1 = derivs(sigma, r, v)
        k2 = derivs(sigma + 0.5 * dt * k1[0], r + 0.5 * dt * k1[1], v + 0.5 * dt * k1[2])
        k3 = derivs(sigma + 0.5 * dt * k2[0], r + 0.5 * dt * k2[1], v + 0.5 * dt * k2[2])
        k4 = derivs(sigma + dt * k3[0], r + dt * k3[1], v + dt * k3[2])

        sigma_new = sigma + (dt / 6.0) * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0])
        r_new = r + (dt / 6.0) * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1])
        v_new = v + (dt / 6.0) * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2])

        if np.linalg.norm(sigma_new) > 1.0:
            sigma_new = shadow(sigma_new)

        self._state = DeadReckoningState(t=sample.t, sigma_BN=sigma_new, r_N=r_new, v_N=v_new)
        return self._state
