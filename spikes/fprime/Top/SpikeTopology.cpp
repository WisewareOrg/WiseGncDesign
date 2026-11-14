#include "Top/SpikeTopology.hpp"

namespace Spike {

void setupTopology(const TopologyState& state) {
    initComponents(state);
    setBaseIds();
    connectComponents();
    configComponents(state);
    regCommands();
    readParameters();
    loadParameters();
    startTasks(state);
}

}  // namespace Spike
