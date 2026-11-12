// The math mirrors imu_dead_reckoning.py and mrp.py term for term, so the two builds can be compared.
#include "algorithms/gnc_algorithms/imu_dead_reckoning/ImuDeadReckoner.hpp"

namespace Gnc {

namespace {

using Eigen::Matrix3d;
using Eigen::Vector3d;

Matrix3d skew(const Vector3d& v) {
    Matrix3d m;
    m << 0.0, -v.z(), v.y(), v.z(), 0.0, -v.x(), -v.y(), v.x(), 0.0;
    return m;
}

//! The MRP kinematics matrix B(sigma), dsigma/dt = 1/4 B(sigma) omega.
Matrix3d kinematics(const Vector3d& sigma) {
    const F64 s2 = sigma.squaredNorm();
    return (1.0 - s2) * Matrix3d::Identity() + 2.0 * skew(sigma) + 2.0 * sigma * sigma.transpose();
}

//! [NB] of an MRP, rotating a body-frame vector into the inertial frame.
Matrix3d dcmNB(const Vector3d& sigma) {
    const F64 s2 = sigma.squaredNorm();
    const Matrix3d sk = skew(sigma);
    return Matrix3d::Identity() + (8.0 * sk * sk + 4.0 * (1.0 - s2) * sk) / ((1.0 + s2) * (1.0 + s2));
}

struct Derivative {
    Vector3d sigma;
    Vector3d r;
    Vector3d v;
};

Derivative derivative(const Vector3d& sigma, const Vector3d& r, const Vector3d& v, const Vector3d& omega,
                      const Vector3d& accel, F64 mu) {
    const F64 rNorm = r.norm();
    return {0.25 * kinematics(sigma) * omega, v, dcmNB(sigma) * accel - mu * r / (rNorm * rNorm * rNorm)};
}

}  // namespace

ImuDeadReckoner::ImuDeadReckoner(const char* compName) : ImuDeadReckonerComponentBase(compName) {}

void ImuDeadReckoner::configure(F64 mu, const Eigen::Matrix3d& dcm_PB) {
    this->m_mu = mu;
    this->m_dcm_BP = dcm_PB.transpose();
    this->m_navState = NavState::idle;
    this->m_t = 0.0;
}

void ImuDeadReckoner::initialize(F64 t, const Eigen::Vector3d& sigma_BN, const Eigen::Vector3d& r_BN_N,
                                 const Eigen::Vector3d& v_BN_N) {
    this->m_t = t;
    this->m_sigma = sigma_BN;
    this->m_r = r_BN_N;
    this->m_v = v_BN_N;
    this->m_navState = NavState::initialized;
    this->writeTelemetry();
}

void ImuDeadReckoner::imuIn_handler(FwIndexType portNum, const Gnc::Vector3& angVelPlatform,
                                    const Gnc::Vector3& accelPlatform) {
    this->m_omega_P = Vector3d(angVelPlatform[0], angVelPlatform[1], angVelPlatform[2]);
    this->m_accel_P = Vector3d(accelPlatform[0], accelPlatform[1], accelPlatform[2]);
}

void ImuDeadReckoner::schedIn_handler(FwIndexType portNum, U32 context) {
    const Fw::Time now = this->getTime();
    const F64 t = static_cast<F64>(now.getSeconds()) + static_cast<F64>(now.getUSeconds()) * 1e-6;
    if (this->m_navState == NavState::idle || !(t > this->m_t)) {
        this->writeTelemetry();
        return;
    }
    const F64 dt = t - this->m_t;
    const Vector3d omega = this->m_dcm_BP * this->m_omega_P;
    const Vector3d accel = this->m_dcm_BP * this->m_accel_P;
    const Vector3d& s = this->m_sigma;
    const Vector3d& r = this->m_r;
    const Vector3d& v = this->m_v;

    const Derivative k1 = derivative(s, r, v, omega, accel, this->m_mu);
    const Derivative k2 = derivative(s + 0.5 * dt * k1.sigma, r + 0.5 * dt * k1.r, v + 0.5 * dt * k1.v, omega,
                                     accel, this->m_mu);
    const Derivative k3 = derivative(s + 0.5 * dt * k2.sigma, r + 0.5 * dt * k2.r, v + 0.5 * dt * k2.v, omega,
                                     accel, this->m_mu);
    const Derivative k4 = derivative(s + dt * k3.sigma, r + dt * k3.r, v + dt * k3.v, omega, accel, this->m_mu);

    Vector3d sigma = s + (dt / 6.0) * (k1.sigma + 2.0 * k2.sigma + 2.0 * k3.sigma + k4.sigma);
    this->m_r = r + (dt / 6.0) * (k1.r + 2.0 * k2.r + 2.0 * k3.r + k4.r);
    this->m_v = v + (dt / 6.0) * (k1.v + 2.0 * k2.v + 2.0 * k3.v + k4.v);
    if (sigma.norm() > 1.0) {
        sigma = -sigma / sigma.squaredNorm();
    }
    this->m_sigma = sigma;
    this->m_t = t;
    this->m_navState = NavState::propagated;
    this->writeTelemetry();
}

void ImuDeadReckoner::writeTelemetry() {
    this->tlmWrite_navState(this->m_navState);
    if (this->m_navState == NavState::idle) {
        return;
    }
    Eigen::Quaterniond q(dcmNB(this->m_sigma));
    if (q.w() < 0.0) {
        q.coeffs() = -q.coeffs();
    }
    this->tlmWrite_bodyEciPosX(this->m_r.x());
    this->tlmWrite_bodyEciPosY(this->m_r.y());
    this->tlmWrite_bodyEciPosZ(this->m_r.z());
    this->tlmWrite_bodyEciVelX(this->m_v.x());
    this->tlmWrite_bodyEciVelY(this->m_v.y());
    this->tlmWrite_bodyEciVelZ(this->m_v.z());
    this->tlmWrite_bodyEciAttitudeW(q.w());
    this->tlmWrite_bodyEciAttitudeX(q.x());
    this->tlmWrite_bodyEciAttitudeY(q.y());
    this->tlmWrite_bodyEciAttitudeZ(q.z());
}

}  // namespace Gnc
