#ifndef SPIKE_SPIKETOPOLOGYDEFS_HPP
#define SPIKE_SPIKETOPOLOGYDEFS_HPP

namespace PingEntries {}

namespace Spike {

//! The state the topology is set up with: the case's parameter file.
struct TopologyState {
    const char* prmPath;
};

}  // namespace Spike

#endif
