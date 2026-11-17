// One constant motor torque on the first wheel, every step: the F´ build of the notebook's spinner.
#ifndef GNC_WHEELSPINNER_HPP
#define GNC_WHEELSPINNER_HPP

#include "algorithms/wheel_spinner/WheelSpinnerComponentAc.hpp"

namespace Gnc {

class WheelSpinner final : public WheelSpinnerComponentBase {
  public:
    explicit WheelSpinner(const char* compName);

  private:
    //! Sends the parameter's torque on the first wheel, the rest zero, and writes it.
    void schedIn_handler(FwIndexType portNum, U32 context) override;
};

}  // namespace Gnc

#endif
