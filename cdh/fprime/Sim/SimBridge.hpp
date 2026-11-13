// The simulation's side of the deployment: feeds sensor readings in and drives the schedule.
#ifndef SIM_SIMBRIDGE_HPP
#define SIM_SIMBRIDGE_HPP

#include "cdh/fprime/Sim/SimBridgeComponentAc.hpp"

namespace Sim {

class SimBridge final : public SimBridgeComponentBase {
  public:
    explicit SimBridge(const char* compName);

    //! Sends the navigation filter its configuration: mu (m^3/s^2) and the IMU's mounting [PB].
    void configureNav(F64 mu, const Gnc::Matrix3& dcmPB);

    //! Sends the navigation filter the state to start from at the current time.
    void initializeNav(const Gnc::Vector3& sigmaBN, const Gnc::Vector3& rBN_N, const Gnc::Vector3& vBN_N);

    //! Sends one IMU reading to the deployment.
    void sendImu(const Gnc::Vector3& angVelPlatform, const Gnc::Vector3& accelPlatform);

    //! Runs every scheduled component once.
    void tick();
};

}  // namespace Sim

#endif
