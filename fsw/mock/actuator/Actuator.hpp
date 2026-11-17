// A test mock both builds fly as an actuator: each step it sends one fixed wheel command.
#ifndef MOCKGNC_ACTUATOR_HPP
#define MOCKGNC_ACTUATOR_HPP

#include "fsw/mock/actuator/ActuatorComponentAc.hpp"

namespace MockGnc {

class Actuator final : public ActuatorComponentBase {
  public:
    explicit Actuator(const char* compName);

  private:
    //! Sends the command: element i is (i + 1) mN*m, as actuator.py's, inside a wheel's torque limit.
    void schedIn_handler(FwIndexType portNum, U32 context) override;
};

}  // namespace MockGnc

#endif
