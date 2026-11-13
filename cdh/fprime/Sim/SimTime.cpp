#include "cdh/fprime/Sim/SimTime.hpp"

namespace Sim {

SimTime::SimTime(const char* compName) : SimTimeComponentBase(compName) {}

void SimTime::set(U64 nanoseconds) {
    this->m_seconds = static_cast<U32>(nanoseconds / 1000000000U);
    this->m_useconds = static_cast<U32>((nanoseconds % 1000000000U) / 1000U);
}

void SimTime::timeGetPort_handler(FwIndexType portNum, Fw::Time& time) {
    time.set(TimeBase::TB_PROC_TIME, 0, this->m_seconds, this->m_useconds);
}

}  // namespace Sim
