#include "fsw/mock/actuator/Actuator.hpp"

namespace MockGnc {

Actuator::Actuator(const char* compName) : ActuatorComponentBase(compName) {}

void Actuator::schedIn_handler(FwIndexType portNum, U32 context) {
    Gnc::WheelCommand command;
    Gnc::WheelCommand::Type_of_motorTorque& torque = command.get_motorTorque();
    for (FwSizeType i = 0; i < sizeof torque / sizeof torque[0]; i++) {
        torque[i] = static_cast<F64>(i + 1) * 1e-3;
    }
    this->wheelOut_out(0, command);
}

}  // namespace MockGnc
