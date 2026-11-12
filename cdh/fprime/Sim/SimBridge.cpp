#include "cdh/fprime/Sim/SimBridge.hpp"

namespace Sim {

SimBridge::SimBridge(const char* compName) : SimBridgeComponentBase(compName) {}

void SimBridge::configureNav(F64 mu, const Gnc::Matrix3& dcmPB) {
    this->navConfigOut_out(0, mu, dcmPB);
}

void SimBridge::initializeNav(const Gnc::Vector3& sigmaBN, const Gnc::Vector3& rBN_N, const Gnc::Vector3& vBN_N) {
    this->navInitOut_out(0, sigmaBN, rBN_N, vBN_N);
}

void SimBridge::sendImu(const Gnc::Vector3& angVelPlatform, const Gnc::Vector3& accelPlatform) {
    this->imuOut_out(0, angVelPlatform, accelPlatform);
}

void SimBridge::tick() {
    for (FwIndexType port = 0; port < this->getNum_schedOut_OutputPorts(); port++) {
        this->schedOut_out(port, 0);
    }
}

}  // namespace Sim
