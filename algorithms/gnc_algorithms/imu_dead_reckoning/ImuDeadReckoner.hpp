// Strapdown inertial dead reckoning from one IMU: the F´ build of the notebook's estimator.
#ifndef GNC_IMUDEADRECKONER_HPP
#define GNC_IMUDEADRECKONER_HPP

#include <Eigen/Dense>

#include "algorithms/gnc_algorithms/imu_dead_reckoning/ImuDeadReckonerComponentAc.hpp"

namespace Gnc {

class ImuDeadReckoner final : public ImuDeadReckonerComponentBase {
  public:
    explicit ImuDeadReckoner(const char* compName);

    //! Boots the estimator idle at t = 0 s, holding mu (m^3/s^2) and the IMU's mounting [PB], v_P = [PB] v_B.
    void configure(F64 mu, const Eigen::Matrix3d& dcm_PB);

    //! Gives the estimate its state at t (s): sigma_BN (MRP), r_BN_N (m) and v_BN_N (m/s).
    //! Temporary: the initNavState command replaces it.
    void initialize(F64 t, const Eigen::Vector3d& sigma_BN, const Eigen::Vector3d& r_BN_N,
                    const Eigen::Vector3d& v_BN_N);

  private:
    void schedIn_handler(FwIndexType portNum, U32 context) override;
    void imuIn_handler(FwIndexType portNum, const Gnc::Vector3& angVelPlatform,
                       const Gnc::Vector3& accelPlatform) override;

    //! Writes every telemetry channel from the held state.
    void writeTelemetry();

    F64 m_mu = 0.0;
    Eigen::Matrix3d m_dcm_BP = Eigen::Matrix3d::Identity();
    NavState m_navState = NavState::idle;
    F64 m_t = 0.0;
    Eigen::Vector3d m_sigma = Eigen::Vector3d::Zero();
    Eigen::Vector3d m_r = Eigen::Vector3d::Zero();
    Eigen::Vector3d m_v = Eigen::Vector3d::Zero();
    Eigen::Vector3d m_omega_P = Eigen::Vector3d::Zero();
    Eigen::Vector3d m_accel_P = Eigen::Vector3d::Zero();
};

}  // namespace Gnc

#endif
