#ifndef GNC_WHEELSPINNER_HPP
#define GNC_WHEELSPINNER_HPP

#include "algorithms/wheel_spinner/WheelSpinnerComponentAc.hpp"

namespace Gnc {

class WheelSpinner final : public WheelSpinnerComponentBase {
  public:
    explicit WheelSpinner(const char* compName);

  private:
    void schedIn_handler(FwIndexType portNum, U32 context) override;
};

}  // namespace Gnc

#endif
