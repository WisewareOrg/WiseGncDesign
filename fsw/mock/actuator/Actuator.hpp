// A test mock both builds fly as an actuator: each step it sends one fixed wheel command and counts it.
#ifndef MOCKGNC_ACTUATOR_HPP
#define MOCKGNC_ACTUATOR_HPP

#include "fsw/mock/actuator/ActuatorComponentAc.hpp"

namespace MockGnc {

class Actuator final : public ActuatorComponentBase {
  public:
    explicit Actuator(const char* compName);

  private:
    //! Counts the step, then sends the command, as actuator.py's.
    void schedIn_handler(FwIndexType portNum, U32 context) override;

    //! Counts the mark, and writes it wide.
    void mark_cmdHandler(FwOpcodeType opCode, U32 cmdSeq) override;

    U64 m_tally = 0;
};

}  // namespace MockGnc

#endif
