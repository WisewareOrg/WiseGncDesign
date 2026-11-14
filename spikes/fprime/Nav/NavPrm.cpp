#include "Nav/NavPrm.hpp"

namespace Nav {

NavPrm::NavPrm(const char* compName) : NavPrmComponentBase(compName) {}

void NavPrm::parametersLoaded() {
    this->loadedCount++;
}

}  // namespace Nav
