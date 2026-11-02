# %% [markdown]
# # Modified Rodrigues parameters
#
# The attitude math the algorithms share. An MRP set $\sigma_{BN}$ describes frame $B$ with
# respect to frame $N$ (Schaub & Junkins): for a rotation by principal angle $\theta$ about
# unit axis $\hat e$, $\sigma = \tan(\theta/4)\,\hat e$. Its norm reaches 1 at
# $\theta = 180°$; the shadow set $-\sigma/|\sigma|^2$ describes the same attitude with the
# reciprocal norm, so switching to it keeps $|\sigma| \le 1$.
#
# With $[\tilde\sigma]$ the cross-product matrix of $\sigma$ and $s^2 = |\sigma|^2$:
#
# $$B(\sigma) = (1 - s^2) I + 2[\tilde\sigma] + 2\sigma\sigma^T \qquad
# \dot\sigma = \tfrac14 B(\sigma)\,\omega_{BN}^B$$
#
# $$[NB] = [BN]^T = I + \frac{8[\tilde\sigma]^2 + 4(1 - s^2)[\tilde\sigma]}{(1 + s^2)^2}$$
#
# Composition and subtraction go through the DCM and back, with the quaternion extracted by
# Shepperd's method so every attitude, including rotations near 180°, converts stably.

# %%
"""Modified Rodrigues parameter (MRP) attitude math: the kinematics matrix, the DCM, the
shadow set, composition, subtraction and the principal angle, all for `sigma_BN`, frame B with
respect to frame N."""

import numpy as np

__all__ = ["B", "angle", "compose", "dcm_NB", "shadow", "subtract"]


# %%
def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def B(sigma: np.ndarray) -> np.ndarray:
    """The (3, 3) MRP kinematics matrix: dsigma/dt = 1/4 B(sigma) @ omega, with omega the
    angular rate of B with respect to N, in B (rad/s)."""
    s2 = float(sigma @ sigma)
    return (1.0 - s2) * np.eye(3) + 2.0 * _skew(sigma) + 2.0 * np.outer(sigma, sigma)


def dcm_NB(sigma: np.ndarray) -> np.ndarray:
    """The (3, 3) DCM [NB] of `sigma` = sigma_BN, rotating a B-frame vector into N:
    v_N = dcm_NB(sigma) @ v_B."""
    s2 = float(sigma @ sigma)
    sk = _skew(sigma)
    return np.eye(3) + (8.0 * (sk @ sk) + 4.0 * (1.0 - s2) * sk) / (1.0 + s2) ** 2


def shadow(sigma: np.ndarray) -> np.ndarray:
    """The shadow set -sigma / |sigma|^2: the same attitude with the reciprocal norm.
    `sigma` is nonzero."""
    s2 = float(sigma @ sigma)
    return -sigma / s2


def _mrp_from_dcm(c: np.ndarray) -> np.ndarray:
    """The MRP of DCM `c` = [BN], with |sigma| <= 1: the quaternion by Shepperd's method,
    sign chosen with a non-negative scalar part, then sigma = q_vec / (1 + q0)."""
    tr = float(np.trace(c))
    largest = int(np.argmax([tr, c[0, 0], c[1, 1], c[2, 2]]))
    if largest == 0:
        q0 = 0.5 * np.sqrt(1.0 + tr)
        q1 = (c[1, 2] - c[2, 1]) / (4.0 * q0)
        q2 = (c[2, 0] - c[0, 2]) / (4.0 * q0)
        q3 = (c[0, 1] - c[1, 0]) / (4.0 * q0)
    elif largest == 1:
        q1 = 0.5 * np.sqrt(1.0 + 2.0 * c[0, 0] - tr)
        q0 = (c[1, 2] - c[2, 1]) / (4.0 * q1)
        q2 = (c[0, 1] + c[1, 0]) / (4.0 * q1)
        q3 = (c[0, 2] + c[2, 0]) / (4.0 * q1)
    elif largest == 2:
        q2 = 0.5 * np.sqrt(1.0 + 2.0 * c[1, 1] - tr)
        q0 = (c[2, 0] - c[0, 2]) / (4.0 * q2)
        q1 = (c[0, 1] + c[1, 0]) / (4.0 * q2)
        q3 = (c[1, 2] + c[2, 1]) / (4.0 * q2)
    else:
        q3 = 0.5 * np.sqrt(1.0 + 2.0 * c[2, 2] - tr)
        q0 = (c[0, 1] - c[1, 0]) / (4.0 * q3)
        q1 = (c[0, 2] + c[2, 0]) / (4.0 * q3)
        q2 = (c[1, 2] + c[2, 1]) / (4.0 * q3)
    q = np.array([q0, q1, q2, q3])
    if q[0] < 0.0:
        q = -q
    return q[1:] / (1.0 + q[0])


def compose(sigma1: np.ndarray, sigma2: np.ndarray) -> np.ndarray:
    """The MRP of `sigma1` followed by `sigma2`: with sigma1 = sigma_AN and sigma2 = sigma_BA,
    returns sigma_BN, so that [BN] = [BA][AN]. The result has |sigma| <= 1."""
    return _mrp_from_dcm(dcm_NB(sigma2).T @ dcm_NB(sigma1).T)


def subtract(sigma1: np.ndarray, sigma2: np.ndarray) -> np.ndarray:
    """`sigma1 ⊖ sigma2`, frame 1 relative to frame 2: with sigma1 = sigma_1N and
    sigma2 = sigma_2N, returns sigma_12, so that [12] = [1N][2N]^T. The result has
    |sigma| <= 1."""
    return _mrp_from_dcm(dcm_NB(sigma1).T @ dcm_NB(sigma2))


def angle(sigma: np.ndarray) -> float:
    """The principal rotation angle of `sigma`, in rad: 4 atan(|sigma|)."""
    return 4.0 * float(np.arctan(np.linalg.norm(sigma)))


# %% [markdown]
# ## Checks
#
# Each check states and verifies one property, against identities or an axis-angle DCM built
# here independently of `dcm_NB`. `run_checks`, at the end, runs every `check_*` function;
# importing the module runs none of them.


# %%
def _dcm_BN_from_axis_angle(axis: np.ndarray, theta: float) -> np.ndarray:
    """[BN] for B rotated from N by `theta` about unit `axis` (Schaub & Junkins eq. 3.62)."""
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    skew_axis = np.array(
        [[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]]
    )
    return cos_t * np.eye(3) + (1.0 - cos_t) * np.outer(axis, axis) - sin_t * skew_axis


# %% [markdown]
# ### Identities at zero and at unit norm
#
# $\sigma = 0$ is the identity attitude, where $[NB] = I$, $B = I$ and the angle is 0;
# $|\sigma| = 1$ is a 180° rotation.


# %%
def check_dcm_at_zero_is_identity() -> None:
    np.testing.assert_allclose(dcm_NB(np.zeros(3)), np.eye(3), atol=1e-12)


def check_b_matrix_at_zero_is_identity() -> None:
    np.testing.assert_allclose(B(np.zeros(3)), np.eye(3), atol=1e-12)


def check_angle_at_zero_is_zero() -> None:
    np.testing.assert_allclose(angle(np.zeros(3)), 0.0, atol=1e-15)


def check_angle_at_unit_norm_is_pi() -> None:
    np.testing.assert_allclose(angle(np.array([1.0, 0.0, 0.0])), np.pi, rtol=1e-12)


# %% [markdown]
# ### The shadow set
#
# Taking the shadow twice returns the original set, and the shadow's norm is the reciprocal.


# %%
def check_shadow_is_self_inverse() -> None:
    sigma = np.array([0.2, -0.1, 0.4])
    np.testing.assert_allclose(shadow(shadow(sigma)), sigma, atol=1e-9)


def check_shadow_has_reciprocal_norm() -> None:
    sigma = np.array([0.2, -0.1, 0.4])
    np.testing.assert_allclose(
        np.linalg.norm(shadow(sigma)), 1.0 / np.linalg.norm(sigma), rtol=1e-12
    )


# %% [markdown]
# ### Composition and subtraction
#
# Subtracting a set from itself gives the identity. Composition matches the DCM product, and
# composing `sigma1 ⊖ sigma2` back onto `sigma2` recovers `sigma1`, which fixes the direction
# of subtraction (a swapped direction also gives zero for equal arguments).


# %%
def check_subtract_from_self_is_zero() -> None:
    sigma = np.array([0.1, 0.2, -0.3])
    np.testing.assert_allclose(subtract(sigma, sigma), np.zeros(3), atol=1e-9)


def check_compose_matches_dcm_product() -> None:
    sigma1 = np.array([0.1, 0.0, 0.0])
    sigma2 = np.array([0.0, 0.15, 0.0])
    np.testing.assert_allclose(
        dcm_NB(compose(sigma1, sigma2)).T, dcm_NB(sigma2).T @ dcm_NB(sigma1).T, atol=1e-9
    )


def check_subtract_direction_recovers_sigma1_via_compose() -> None:
    sigma1 = np.array([0.1, 0.2, -0.3])
    sigma2 = np.array([-0.2, 0.05, 0.1])
    np.testing.assert_allclose(compose(sigma2, subtract(sigma1, sigma2)), sigma1, atol=1e-9)


# %% [markdown]
# ### Composition near 180° takes each of Shepperd's non-trace branches
#
# Near the identity the quaternion extraction always picks its trace branch. Composing two
# 85° rotations about an axis tilted towards x, y or z makes that axis's diagonal entry the
# largest candidate, exercising the other three branches; tilting off the principal axes keeps
# every off-diagonal term in the chosen branch nonzero, so a sign or index error shows.


# %%
def check_compose_near_180_degrees_takes_each_non_trace_branch() -> None:
    theta_half = np.radians(85.0)
    for branch, raw_axis in enumerate(([1.0, 0.3, 0.2], [0.3, 1.0, 0.2], [0.3, 0.2, 1.0]), 1):
        axis = np.asarray(raw_axis) / np.linalg.norm(raw_axis)
        sigma_half = np.tan(theta_half / 4.0) * axis
        np.testing.assert_allclose(
            dcm_NB(compose(sigma_half, sigma_half)).T,
            _dcm_BN_from_axis_angle(axis, 2.0 * theta_half),
            atol=1e-7,
            err_msg=f"Shepperd branch {branch}",
        )


# %% [markdown]
# ## Running the checks
#
# `run_checks` runs every `check_*` function above and prints a one-line summary, when this
# module executes as `__main__`: `python -m gnc_algorithms.mrp`, or this notebook's cells run
# top to bottom in a kernel.


# %%
def run_checks() -> None:
    """Runs every `check_*` function in this module, in definition order."""
    checks = [obj for name, obj in globals().items() if name.startswith("check_")]
    for check in checks:
        check()
    print(f"mrp: {len(checks)} checks passed")


if __name__ == "__main__":
    run_checks()
