#include "fsw/fprime/rio/SimBridge.hpp"

namespace Sim {

SimBridge::SimBridge(const char* compName) : SimBridgeComponentBase(compName) {}

void SimBridge::sendImu(const Gnc::Vector3& angVelPlatform, const Gnc::Vector3& accelPlatform) {
    this->imuOut_out(0, Gnc::ImuReading(angVelPlatform, accelPlatform));
}

}  // namespace Sim
