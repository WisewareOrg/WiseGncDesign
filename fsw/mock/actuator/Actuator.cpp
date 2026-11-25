#include "fsw/mock/actuator/Actuator.hpp"

namespace MockGnc {

Actuator::Actuator(const char* compName) : ActuatorComponentBase(compName) {}

void Actuator::mark_cmdHandler(FwOpcodeType opCode, U32 cmdSeq) {
    this->tlmWrite_tally(++this->m_tally);
    Wide wide;
    for (FwSizeType i = 0; i < Wide::SIZE; i++) {
        wide[i] = 1000.0 * this->m_tally + static_cast<F64>(i);
    }
    this->tlmWrite_wide(wide);
    this->cmdResponse_out(opCode, cmdSeq, Fw::CmdResponse::OK);
}

void Actuator::schedIn_handler(FwIndexType /*portNum*/, U32 /*context*/) {
    this->tlmWrite_tally(++this->m_tally);
    Gnc::WheelCommand command;
    Gnc::WheelCommand::Type_of_motorTorque& torque = command.get_motorTorque();
    for (FwSizeType i = 0; i < sizeof torque / sizeof torque[0]; i++) {
        torque[i] = static_cast<F64>(i + 1) * 1e-3;
    }
    this->wheelOut_out(0, command);
}

}  // namespace MockGnc
