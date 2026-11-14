#include "fsw/fprime/rio/SimBridge.hpp"

namespace Sim {

SimBridge::SimBridge(const char* compName) : SimBridgeComponentBase(compName) {}

void SimBridge::configureNav(F64 mu, const Gnc::Matrix3& dcmPB) {
    this->navConfigOut_out(0, mu, dcmPB);
}

void SimBridge::sendImu(const Gnc::Vector3& angVelPlatform, const Gnc::Vector3& accelPlatform) {
    this->imuOut_out(0, Gnc::ImuReading(angVelPlatform, accelPlatform));
}

}  // namespace Sim
