// The command is wheel_spinner.py's; fprime_test.py holds the two builds to it step for step.
#include "algorithms/wheel_spinner/WheelSpinner.hpp"

namespace Gnc {

WheelSpinner::WheelSpinner(const char* compName) : WheelSpinnerComponentBase(compName) {}

void WheelSpinner::schedIn_handler(FwIndexType portNum, U32 context) {
    Fw::ParamValid valid;
    const F64 torque = this->paramGet_motorTorque(valid);
    FW_ASSERT(valid == Fw::ParamValid::VALID, valid.e);
    Gnc::WheelCommand command;
    Gnc::WheelCommand::Type_of_motorTorque& motorTorque = command.get_motorTorque();
    for (FwSizeType i = 0; i < sizeof motorTorque / sizeof motorTorque[0]; i++) {
        motorTorque[i] = 0.0;
    }
    motorTorque[0] = torque;
    this->wheelOut_out(0, command);
    this->tlmWrite_wheelTorque(torque);
}

}  // namespace Gnc
