#include "cdh/fprime/Sim/SimTime.hpp"

#include <cmath>

namespace Sim {

SimTime::SimTime(const char* compName) : SimTimeComponentBase(compName) {}

void SimTime::set(F64 seconds) {
    const F64 whole = std::floor(seconds);
    this->m_seconds = static_cast<U32>(whole);
    this->m_useconds = static_cast<U32>(std::llround((seconds - whole) * 1e6));
}

void SimTime::timeGetPort_handler(FwIndexType portNum, Fw::Time& time) {
    time.set(TimeBase::TB_PROC_TIME, 0, this->m_seconds, this->m_useconds);
}

}  // namespace Sim
