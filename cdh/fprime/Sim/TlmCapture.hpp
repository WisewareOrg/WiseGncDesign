// Holds the latest serialized value of every telemetry channel, for the simulation to read.
#ifndef SIM_TLMCAPTURE_HPP
#define SIM_TLMCAPTURE_HPP

#include <map>
#include <vector>

#include "cdh/fprime/Sim/TlmCaptureComponentAc.hpp"

namespace Sim {

class TlmCapture final : public TlmCaptureComponentBase {
  public:
    explicit TlmCapture(const char* compName);

    //! The latest serialized value of each channel, as F´ sends it, by channel ID.
    const std::map<FwChanIdType, std::vector<U8>>& latest() const;

    //! Forgets every sample.
    void clear();

  private:
    void TlmRecv_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;

    std::map<FwChanIdType, std::vector<U8>> m_latest;
};

}  // namespace Sim

#endif
