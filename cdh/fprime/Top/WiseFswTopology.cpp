#include "cdh/fprime/Top/WiseFswTopology.hpp"

namespace WiseFsw {

void setupTopology(const TopologyState& state) {
    initComponents(state);
    setBaseIds();
    connectComponents();
    configComponents(state);
    regCommands();
    startTasks(state);
}

}  // namespace WiseFsw
