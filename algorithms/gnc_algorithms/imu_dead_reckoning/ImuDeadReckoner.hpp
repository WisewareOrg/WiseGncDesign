// Strapdown inertial dead reckoning from one IMU: the F´ build of the notebook's estimator.
#ifndef GNC_IMUDEADRECKONER_HPP
#define GNC_IMUDEADRECKONER_HPP

#include <Eigen/Dense>

#include "algorithms/gnc_algorithms/imu_dead_reckoning/ImuDeadReckonerComponentAc.hpp"

namespace Gnc {

class ImuDeadReckoner final : public ImuDeadReckonerComponentBase {
  public:
    explicit ImuDeadReckoner(const char* compName);

  private:
    void schedIn_handler(FwIndexType portNum, U32 context) override;
    void imuIn_handler(FwIndexType portNum, const Gnc::Vector3& angVelPlatform,
                       const Gnc::Vector3& accelPlatform) override;
    void configureIn_handler(FwIndexType portNum, F64 mu, const Gnc::Matrix3& dcmPB) override;
    void initNavState_cmdHandler(FwOpcodeType opCode, U32 cmdSeq, F64 epoch, const Gnc::Quaternion& attitude,
                                 const Gnc::Vector3& position, const Gnc::Vector3& velocity) override;

    //! The clock's time, in s.
    F64 now();

    //! Writes every telemetry channel from the held state.
    void writeTelemetry();

    F64 m_mu = 0.0;
    Eigen::Matrix3d m_dcm_BP = Eigen::Matrix3d::Identity();
    NavState m_navState = NavState::idle;
    F64 m_t = 0.0;
    //! Body to ECI, unit, W >= 0.
    Eigen::Quaterniond m_q = Eigen::Quaterniond::Identity();
    Eigen::Vector3d m_r = Eigen::Vector3d::Zero();
    Eigen::Vector3d m_v = Eigen::Vector3d::Zero();
    Eigen::Vector3d m_omega_P = Eigen::Vector3d::Zero();
    Eigen::Vector3d m_accel_P = Eigen::Vector3d::Zero();
};

}  // namespace Gnc

#endif
