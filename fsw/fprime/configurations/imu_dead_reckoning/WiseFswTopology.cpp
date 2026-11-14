#include "fsw/fprime/configurations/imu_dead_reckoning/WiseFswTopology.hpp"

#include "fsw/fpp/gnc/FppConstantsAc.hpp"

namespace WiseFsw {

namespace {

//! Each driver output's divider of the base tick, from the GNC sub-topology's constants; 0 leaves an output idle.
const Svc::RateGroupDriver::DividerSet rateGroupDividers{{{ImuDeadReckoning::navDivider, 0}, {0, 0}, {0, 0}}};

//! The context nav's rate group passes its members: unused.
const Svc::PassiveRateGroup::ContextArray navRateGroupContexts(0);

void configureTopology() {
    rateGroupDriver.configure(rateGroupDividers);
    ImuDeadReckoning::navRateGroup.configure(navRateGroupContexts);
}

}  // namespace

void setupTopology(const TopologyState& state) {
    initComponents(state);
    setBaseIds();
    connectComponents();
    configComponents(state);
    configureTopology();
    regCommands();
    startTasks(state);
}

}  // namespace WiseFsw
