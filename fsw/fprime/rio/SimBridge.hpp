// The simulation's side of the deployment: feeds sensor readings in.
#ifndef SIM_SIMBRIDGE_HPP
#define SIM_SIMBRIDGE_HPP

#include "fsw/fprime/rio/SimBridgeComponentAc.hpp"

namespace Sim {

class SimBridge final : public SimBridgeComponentBase {
  public:
    explicit SimBridge(const char* compName);

    //! Sends one IMU reading to the deployment.
    void sendImu(const Gnc::Vector3& angVelPlatform, const Gnc::Vector3& accelPlatform);
};

}  // namespace Sim

#endif
