// The deployment's clock: the simulation sets it before each tick.
#ifndef SIM_SIMTIME_HPP
#define SIM_SIMTIME_HPP

#include "cdh/fprime/Sim/SimTimeComponentAc.hpp"

namespace Sim {

class SimTime final : public SimTimeComponentBase {
  public:
    explicit SimTime(const char* compName);

    //! Sets the time every component reads, in s since the simulation's start.
    void set(F64 seconds);

  private:
    void timeGetPort_handler(FwIndexType portNum, Fw::Time& time) override;

    U32 m_seconds = 0;
    U32 m_useconds = 0;
};

}  // namespace Sim

#endif
