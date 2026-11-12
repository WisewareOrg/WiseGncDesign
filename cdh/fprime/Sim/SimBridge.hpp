// The simulation's side of the deployment: feeds sensor readings in and drives the schedule.
#ifndef SIM_SIMBRIDGE_HPP
#define SIM_SIMBRIDGE_HPP

#include "cdh/fprime/Sim/SimBridgeComponentAc.hpp"

namespace Sim {

class SimBridge final : public SimBridgeComponentBase {
  public:
    explicit SimBridge(const char* compName);

    //! Sends one IMU reading to the deployment.
    void sendImu(const Gnc::Vector3& angVelPlatform, const Gnc::Vector3& accelPlatform);

    //! Runs every scheduled component once.
    void tick();
};

}  // namespace Sim

#endif
