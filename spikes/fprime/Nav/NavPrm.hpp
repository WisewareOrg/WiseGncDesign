#ifndef NAV_NAVPRM_HPP
#define NAV_NAVPRM_HPP

#include "Nav/NavPrmComponentAc.hpp"

namespace Nav {

class NavPrm final : public NavPrmComponentBase {
  public:
    explicit NavPrm(const char* compName);

    F64 mu(Fw::ParamValid& valid) { return this->paramGet_mu(valid); }
    Matrix3 dcm_PB(Fw::ParamValid& valid) { return this->paramGet_dcm_PB(valid); }

    U32 loadedCount = 0;

  private:
    void parametersLoaded() override;
};

}  // namespace Nav

#endif
