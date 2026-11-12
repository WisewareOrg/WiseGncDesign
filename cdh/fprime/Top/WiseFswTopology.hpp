// Sets up and tears down the WiseFsw deployment.
#ifndef WISEFSW_WISEFSWTOPOLOGY_HPP
#define WISEFSW_WISEFSWTOPOLOGY_HPP

#include "cdh/fprime/Top/WiseFswTopologyAc.hpp"

namespace WiseFsw {

void setupTopology(const TopologyState& state);
void teardownTopology(const TopologyState& state);

}  // namespace WiseFsw

#endif
