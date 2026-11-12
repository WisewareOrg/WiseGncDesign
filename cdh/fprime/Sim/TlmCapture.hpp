// Holds the latest serialized value and time of every telemetry channel, for the simulation to read.
#ifndef SIM_TLMCAPTURE_HPP
#define SIM_TLMCAPTURE_HPP

#include <map>
#include <vector>

#include "cdh/fprime/Sim/TlmCaptureComponentAc.hpp"

namespace Sim {

class TlmCapture final : public TlmCaptureComponentBase {
  public:
    struct Sample {
        F64 time;                //!< s, the value's time tag
        std::vector<U8> value;  //!< the value, serialized as F´ sends it
    };

    explicit TlmCapture(const char* compName);

    //! The latest sample of each channel, by channel ID.
    const std::map<FwChanIdType, Sample>& latest() const;

    //! Forgets every sample.
    void clear();

  private:
    void TlmRecv_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;

    std::map<FwChanIdType, Sample> m_latest;
};

}  // namespace Sim

#endif
