#include "cdh/fprime/Top/WiseFswTopology.hpp"

namespace WiseFsw {

void setupTopology(const TopologyState& state) {
    initComponents(state);
    setBaseIds();
    connectComponents();
    configComponents(state);
}

void teardownTopology(const TopologyState& state) {
    tearDownComponents(state);
    deinitComponents(state);
}

}  // namespace WiseFsw
