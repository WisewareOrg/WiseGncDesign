// The math is imu_dead_reckoning.py's; parity.py holds the two builds to parity case by case.
#include "algorithms/imu_dead_reckoning/ImuDeadReckoner.hpp"

#include "algorithms/utils/rk4/Rk4.hpp"

namespace Gnc {

namespace {

using Eigen::Quaterniond;
using Eigen::Vector3d;
using Eigen::Vector4d;

//! The state x = (q, r, v), q W X Y Z.
using State = Eigen::Matrix<F64, 10, 1>;

Quaterniond quaternion(const Vector4d& wxyz) {
    return Quaterniond(wxyz[0], wxyz[1], wxyz[2], wxyz[3]);
}

Vector4d wxyz(const Quaterniond& q) {
    return Vector4d(q.w(), q.x(), q.y(), q.z());
}

//! dx/dt: dq/dt = 1/2 q (x) (0, omega), dr/dt = v, dv/dt = [NB](q) accel - mu r / |r|^3, [NB] of q as it
//! stands.
State derivative(F64 t, const State& x, const Vector3d& omega, const Vector3d& accel, F64 mu) {
    const Quaterniond rotation = quaternion(x.head<4>());
    const Vector3d r = x.segment<3>(4);
    const Quaterniond qdot = rotation * Quaterniond(0.0, omega.x(), omega.y(), omega.z());
    const F64 rNorm = r.norm();
    State xDot;
    xDot << 0.5 * wxyz(qdot), x.tail<3>(), rotation.toRotationMatrix() * accel - mu * r / (rNorm * rNorm * rNorm);
    return xDot;
}

Vector3d vector(const Gnc::Vector3& v) {
    return Vector3d(v[0], v[1], v[2]);
}

Eigen::Matrix3d matrix(const Gnc::Matrix3& m) {
    Eigen::Matrix3d out;
    out << vector(m[0]).transpose(), vector(m[1]).transpose(), vector(m[2]).transpose();
    return out;
}

}  // namespace

ImuDeadReckoner::ImuDeadReckoner(const char* compName) : ImuDeadReckonerComponentBase(compName) {}

F64 ImuDeadReckoner::now() {
    const Fw::Time time = this->getTime();
    return static_cast<F64>(time.getSeconds()) + static_cast<F64>(time.getUSeconds()) * 1e-6;
}

void ImuDeadReckoner::initNavState_cmdHandler(FwOpcodeType opCode, U32 cmdSeq, F64 epoch,
                                              const Gnc::Quaternion& attitude, const Gnc::Vector3& position,
                                              const Gnc::Vector3& velocity) {
    this->m_t = epoch;
    const F64 sign = attitude[0] < 0.0 ? -1.0 : 1.0;
    this->m_q = Quaterniond(sign * attitude[0], sign * attitude[1], sign * attitude[2], sign * attitude[3]);
    this->m_r = vector(position);
    this->m_v = vector(velocity);
    this->m_navState = NavState::initialized;
    this->tlmWrite_navState(this->m_navState);
    this->cmdResponse_out(opCode, cmdSeq, Fw::CmdResponse::OK);
}

void ImuDeadReckoner::imuIn_handler(FwIndexType portNum, const Gnc::ImuReading& reading) {
    this->m_omega_P = vector(reading.get_angVelPlatform());
    this->m_accel_P = vector(reading.get_accelPlatform());
}

void ImuDeadReckoner::schedIn_handler(FwIndexType portNum, U32 context) {
    const F64 t = this->now();
    if (this->m_navState == NavState::idle) {
        this->writeTelemetry();
        return;
    }
    Fw::ParamValid valid;
    const F64 mu = this->paramGet_mu(valid);
    FW_ASSERT(valid == Fw::ParamValid::VALID, valid.e);
    const Eigen::Matrix3d dcm_BP = matrix(this->paramGet_dcm_PB(valid)).transpose();
    FW_ASSERT(valid == Fw::ParamValid::VALID, valid.e);

    const F64 dt = t - this->m_t;
    const Vector3d omega = dcm_BP * this->m_omega_P;
    const Vector3d accel = dcm_BP * this->m_accel_P;
    State x;
    x << wxyz(this->m_q), this->m_r, this->m_v;
    x = Rk4::step(derivative, 0.0, x, dt, omega, accel, mu);

    Vector4d qNew = x.head<4>();
    qNew /= qNew.norm();
    if (qNew[0] < 0.0) {
        qNew = -qNew;
    }
    this->m_q = quaternion(qNew);
    this->m_r = x.segment<3>(4);
    this->m_v = x.tail<3>();
    this->m_t = t;
    this->m_navState = NavState::propagated;
    this->writeTelemetry();
}

void ImuDeadReckoner::writeTelemetry() {
    this->tlmWrite_navState(this->m_navState);
    if (this->m_navState == NavState::idle) {
        return;
    }
    const Quaterniond& q = this->m_q;
    this->tlmWrite_bodyEciPos(Gnc::Vector3({this->m_r.x(), this->m_r.y(), this->m_r.z()}));
    this->tlmWrite_bodyEciVel(Gnc::Vector3({this->m_v.x(), this->m_v.y(), this->m_v.z()}));
    this->tlmWrite_bodyEciAttitude(Gnc::Quaternion({q.w(), q.x(), q.y(), q.z()}));
}

}  // namespace Gnc
