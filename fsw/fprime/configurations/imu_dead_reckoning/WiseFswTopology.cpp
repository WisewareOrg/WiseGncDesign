#include "fsw/fprime/configurations/imu_dead_reckoning/WiseFswTopology.hpp"

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
